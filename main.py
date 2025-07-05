# === PYTHON 3.13 PATCH ===
import sys, types
sys.modules['audioop'] = types.SimpleNamespace()

# === Imports ===
import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, pytz
from datetime import datetime
from flask import Flask
from threading import Thread
from pymongo import MongoClient

# === Flask for Uptime Pinging ===
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ EpicGambler Bot is running!"
def run_flask():
    app.run(host="0.0.0.0", port=8080)

# === Discord Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# === MongoDB Setup ===
mongo_uri = os.getenv("EPICDB")
mongo_client = MongoClient(mongo_uri)
db = mongo_client["epicgambler"]
userdata = db["users"]

# === Uptime Tracker ===
tz = pytz.timezone("Asia/Kolkata")
start_time = datetime.now(tz)
last_update_time = None
status_channel_id = 1391135487502192740  # 🔁 Replace with your channel ID
status_message_id = 123456789012345678  # 🔁 Replace with your message ID

def format_uptime(delta):
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days:02}d:{hours:02}h:{minutes:02}m:{seconds:02}s"

def current_ist_time():
    return datetime.now(tz).strftime("%H:%M:%S")

@tasks.loop(seconds=55)
async def update_uptime():
    global last_update_time
    now = datetime.now(tz)
    uptime = format_uptime(now - start_time)
    last_update_time = now.strftime("%H:%M:%S")

    embed = discord.Embed(title="🎲 EPIC GAMBLER BOT", color=discord.Color.green())
    embed.add_field(name="🟩 STATUS", value="ONLINE ✅", inline=False)
    embed.add_field(name="🕒 START TIME", value=start_time.strftime("%I:%M %p IST"), inline=False)
    embed.add_field(name="⏱ UPTIME", value=uptime, inline=False)
    embed.add_field(name="🛎 LAST UPDATE", value=f"{last_update_time} IST", inline=False)

    try:
        channel = bot.get_channel(status_channel_id)
        msg = await channel.fetch_message(status_message_id)
        await msg.edit(embed=embed)
    except Exception as e:
        print(f"[UPTIME UPDATE ERROR] {e}")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"⚠️ Slash sync error: {e}")
    update_uptime.start()

# === /msgsend Command ===
@bot.tree.command(name="msgsend", description="Send a message to a specific channel")
@app_commands.describe(channel_id="Channel ID", message="Message to send")
async def msgsend(interaction: discord.Interaction, channel_id: str, message: str):
    channel = bot.get_channel(int(channel_id))
    if channel:
        await channel.send(message)
        await interaction.response.send_message(f"✅ Message sent to <#{channel_id}>", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Invalid channel ID", ephemeral=True)

# === Main Run ===
if __name__ == "__main__":
    Thread(target=run_flask).start()
    token = os.getenv("EPIC")
    if not token:
        print("❌ 'EPIC' env variable missing!")
        exit()
    bot.run(token)
