import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import asyncpg
import random
import datetime
import os
import requests
from flask import Flask
from threading import Thread

TOKEN = os.getenv("EPIC")
DATABASE_URL = os.getenv("DATABASE_URL")
GUILD_ID = 123456789012345678  # Replace with your server ID
HELP_CHANNEL_ID = 123456789012345678  # Replace with your help channel
UPTIME_CHANNEL_ID = 123456789012345678  # Replace with uptime embed channel
UPTIME_MESSAGE_ID = 123456789012345678  # Replace with embed message ID
ADMIN_ROLE_ID = 123456789012345678  # Role that can manage shop
SPS_CHANNEL_ID = 123456789012345678  # #sps channel ID
GENERAL_CHANNEL_ID = 123456789012345678  # #general for quiz

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

start_time = datetime.datetime.now(datetime.timezone.utc)
db_pool = None

# ------------------ FLASK SERVER FOR RENDER PING ------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is alive"

Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# ------------------ DATABASE SETUP ------------------
async def create_tables():
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                coins BIGINT DEFAULT 0,
                last_spin DATE
            );
            CREATE TABLE IF NOT EXISTS shop (
                id SERIAL PRIMARY KEY,
                name TEXT,
                description TEXT,
                price INT,
                image TEXT,
                reward TEXT
            );
        """)

async def add_user(user_id):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id) VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING;
        """, user_id)

async def update_coins(user_id, amount):
    await add_user(user_id)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET coins = coins + $1 WHERE user_id = $2;
        """, amount, user_id)

async def get_coins(user_id):
    await add_user(user_id)
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT coins FROM users WHERE user_id = $1", user_id)

async def redeem_item(user_id, item_id):
    async with db_pool.acquire() as conn:
        item = await conn.fetchrow("SELECT * FROM shop WHERE id = $1", item_id)
        if not item:
            return None
        coins = await get_coins(user_id)
        if coins < item["price"]:
            return False
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id = $2", item["price"], user_id)
        return item

# ------------------ UPTIME EMBED ------------------
@tasks.loop(seconds=55)
async def update_uptime():
    channel = bot.get_channel(UPTIME_CHANNEL_ID)
    if not channel:
        return
    try:
        msg = await channel.fetch_message(UPTIME_MESSAGE_ID)
        now = datetime.datetime.now(datetime.timezone.utc)
        uptime = str(now - start_time).split(".")[0]
        embed = discord.Embed(title="EpicGambler Bot Status", color=discord.Color.green())
        embed.add_field(name="Start Time (IST)", value=start_time.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S"))
        embed.add_field(name="Uptime", value=uptime)
        embed.set_footer(text="Last Update (IST): " + now.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S"))
        await msg.edit(embed=embed)
    except Exception as e:
        print("Uptime update failed:", e)

# ------------------ HELP COMMAND ------------------
@tree.command(name="help", description="Show help info")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="EpicGambler Bot Help", color=discord.Color.blurple())
    embed.add_field(name="/help", value="Show this menu", inline=False)
    embed.add_field(name="Quiz", value="Bot will randomly ask a question in #general", inline=False)
    embed.add_field(name="/play", value="Play rock paper scissors in #sps", inline=False)
    embed.add_field(name="/spin", value="Spin to win (daily)", inline=False)
    embed.add_field(name="/shop", value="See redeemable items", inline=False)
    embed.add_field(name="/redeem <id>", value="Redeem an item using EGO Coins", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ------------------ SHOP COMMANDS ------------------
@tree.command(name="shop", description="View all shop items")
async def shop(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        items = await conn.fetch("SELECT * FROM shop")
    embed = discord.Embed(title="Shop Items", color=discord.Color.orange())
    for item in items:
        embed.add_field(name=f"{item['id']}: {item['name']} ({item['price']}🪙)", value=item['description'], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="redeem", description="Redeem a shop item")
@app_commands.describe(id="ID of the item")
async def redeem(interaction: discord.Interaction, id: int):
    item = await redeem_item(interaction.user.id, id)
    if item is None:
        await interaction.response.send_message("Invalid item ID.", ephemeral=True)
    elif item is False:
        await interaction.response.send_message("Not enough coins.", ephemeral=True)
    else:
        await interaction.response.send_message(f"You redeemed **{item['name']}**! Check your DMs!", ephemeral=True)
        await interaction.user.send(f"Thanks for redeeming **{item['name']}**!\nDownload: {item['reward']}")

@tree.command(name="add_shop", description="Admin: Add a shop item")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def add_shop(interaction: discord.Interaction, name: str, desc: str, price: int, image: str, reward: str):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO shop (name, description, price, image, reward) VALUES ($1,$2,$3,$4,$5)", name, desc, price, image, reward)
    await interaction.response.send_message(f"Item **{name}** added!", ephemeral=True)

# ------------------ QUIZ ------------------
async def post_quiz():
    q = requests.get("https://opentdb.com/api.php?amount=1&type=multiple").json()["results"][0]
    question = q["question"]
    correct = q["correct_answer"]
    options = q["incorrect_answers"] + [correct]
    random.shuffle(options)
    channel = bot.get_channel(GENERAL_CHANNEL_ID)
    msg = await channel.send(f"**Quiz Time!**\n{question}\nOptions: {', '.join(options)}")

    def check(m):
        return m.channel.id == channel.id and m.content.lower() == correct.lower()

    try:
        winner = await bot.wait_for('message', check=check, timeout=60)
        await update_coins(winner.author.id, 10)
        await channel.send(f"Correct! {winner.author.mention} gets 10🪙!")
    except asyncio.TimeoutError:
        await channel.send("Time's up! No one answered correctly.")

@tasks.loop(minutes=30)
async def quiz_loop():
    await post_quiz()

# ------------------ ROCK PAPER SCISSORS ------------------
@tree.command(name="play", description="Play Rock Paper Scissors")
async def play(interaction: discord.Interaction):
    if interaction.channel.id != SPS_CHANNEL_ID:
        return await interaction.response.send_message("Only usable in #sps", ephemeral=True)
    await interaction.response.send_message("Choose: rock, paper, or scissors")

    def check(msg):
        return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id and msg.content.lower() in ["rock", "paper", "scissors"]

    try:
        msg = await bot.wait_for("message", check=check, timeout=20)
    except asyncio.TimeoutError:
        return await interaction.followup.send("Timed out!", ephemeral=True)

    user = msg.content.lower()
    bot_choice = random.choices(["rock", "paper", "scissors"], weights=[0.3, 0.4, 0.3])[0]
    await interaction.followup.send(f"Bot chose {bot_choice}")
    if user == bot_choice:
        await interaction.channel.send("It's a tie!")
    elif (user == "rock" and bot_choice == "scissors") or (user == "paper" and bot_choice == "rock") or (user == "scissors" and bot_choice == "paper"):
        await update_coins(interaction.user.id, 5)
        await interaction.channel.send(f"{interaction.user.mention} wins and earns 5🪙!")
    else:
        await interaction.channel.send(f"Bot wins!")

# ------------------ SPIN SYSTEM ------------------
@tree.command(name="spin", description="Spin the lucky wheel!")
async def spin(interaction: discord.Interaction):
    today = datetime.date.today()
    async with db_pool.acquire() as conn:
        last = await conn.fetchval("SELECT last_spin FROM users WHERE user_id = $1", interaction.user.id)
        await add_user(interaction.user.id)
        if last == today:
            await interaction.response.send_message("You've already spun today. Try again tomorrow!", ephemeral=True)
            return
        reward = random.choices([5, 10, 20, 50, 100, 200], weights=[40, 30, 15, 10, 4, 1])[0]
        await conn.execute("UPDATE users SET coins = coins + $1, last_spin = $2 WHERE user_id = $3", reward, today, interaction.user.id)
    await interaction.response.send_message(f"You spun the wheel and won {reward}🪙!", ephemeral=True)

# ------------------ EVENTS ------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await update_coins(message.author.id, 1)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    await create_tables()
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    update_uptime.start()
    quiz_loop.start()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
