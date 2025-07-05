# === PYTHON 3.13 PATCH ===
import sys, types
sys.modules['audioop'] = types.SimpleNamespace()  # Fix for Python 3.13.4 crash

# === Imports ===
import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask
from threading import Thread
from datetime import datetime
import pytz, os
from pymongo import MongoClient

# === MongoDB Setup ===
MONGO_URI = os.getenv("EPICDB")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["epicbotdb"]
users_collection = db["users"]

# === Flask Server (Uptime Ping) ===
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ EpicGambler Bot is running!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

# === Discord Bot Setup ===
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

tz = pytz.timezone("Asia/Kolkata")
start_time = datetime.now(tz)
last_downtime = None

# === HARD CODED UPTIME CONFIG ===
UPTIME_CHANNEL_ID = 1391135487502192740  # Replace with your channel ID
UPTIME_MESSAGE_ID = 123456789012345678  # Replace with your message ID

def format_uptime(delta):
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days:02}d:{hours:02}h:{minutes:02}m:{seconds:02}s"

@tasks.loop(seconds=55)
async def update_uptime():
    now = datetime.now(tz)
    uptime = format_uptime(now - start_time)
    last_update_time = now.strftime("%I:%M:%S %p")

    embed = discord.Embed(title="🧠 EPIC GAMBLER BOT", color=discord.Color.green())
    embed.add_field(name="🟢 STATUS", value="ONLINE", inline=True)
    embed.add_field(name="🕒 START TIME", value=start_time.strftime("%I:%M %p IST"), inline=True)
    embed.add_field(name="⏱ UPTIME", value=uptime, inline=True)
    embed.add_field(name="🛎️ LAST UPDATE", value=last_update_time, inline=True)
    embed.set_footer(text="Updated every 55s")

    channel = bot.get_channel(UPTIME_CHANNEL_ID)
    if not channel:
        print("Uptime channel not found!")
        return

    try:
        message = await channel.fetch_message(UPTIME_MESSAGE_ID)
        await message.edit(embed=embed)
    except Exception as e:
        print(f"❌ Failed to update uptime embed: {e}")

@bot.event
async def on_connect():
    global start_time, last_downtime
    now = datetime.now(tz)
    if start_time:
        last_downtime = now
    start_time = now

@bot.tree.command(name="msgsend", description="Send a message to a channel")
@app_commands.describe(channel="Target channel", message="Message to send")
async def msgsend(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    await channel.send(message)
    await interaction.response.send_message("✅ Message sent!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("🔄 Slash commands synced.")
    except Exception as e:
        print(f"⚠️ Sync error: {e}")
    update_uptime.start()

# === Main Runner ===
if __name__ == "__main__":
    Thread(target=run_flask).start()
    TOKEN = os.getenv("EPIC")
    if not TOKEN:
        print("❌ EPIC not set in environment!")
        exit()
    bot.run(TOKEN)
