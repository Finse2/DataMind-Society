import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
from datetime import datetime
import pytz

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

secret_role = "Trusted"

def get_users_from_list():
    """Read existing users from User_List file."""
    users = set()
    try:
        with open("User_List", "r", encoding="utf-8") as f:
            for line in f:
                # Extract username (everything before " - Joined:")
                if " - Joined:" in line:
                    username = line.split(" - Joined:")[0].strip()
                else:
                    # Handle old format without timestamp
                    username = line.strip()
                if username:
                    users.add(username)
    except FileNotFoundError:
        pass
    return users

async def sync_users_to_list():
    """Check all members on server and add any missing ones to User_List."""
    cet = pytz.timezone('Europe/Berlin')
    current_time = datetime.now(cet).strftime("%Y-%m-%d %H:%M:%S CET")
    existing_users = get_users_from_list()
    
    # Get all members from all guilds
    all_members = set()
    for guild in bot.guilds:
        for member in guild.members:
            if not member.bot:  # Exclude bots
                all_members.add(member.name)
    
    # Find missing members
    missing_members = all_members - existing_users
    
    # Add missing members to the list
    if missing_members:
        with open("User_List", "a", encoding="utf-8") as f:
            for member_name in sorted(missing_members):
                f.write(f"{member_name} - Joined: {current_time}\n")
        print(f"Added {len(missing_members)} missing member(s) to User_List")

@tasks.loop(hours=1)
async def hourly_sync():
    """Sync users every hour."""
    await sync_users_to_list()

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")
    # Initial sync at startup
    await sync_users_to_list()
    # Start hourly sync task
    hourly_sync.start()

@bot.event
async def on_member_remove(member):
    # Remove member name from User_List
    try:
        with open("User_List", "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open("User_List", "w", encoding="utf-8") as f:
            for line in lines:
                # Check if line starts with member name (handles both old format and new format with timestamp)
                if not line.strip().startswith(member.name):
                    f.write(line)
    except FileNotFoundError:
        pass

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to the server {member.name}")
    # Add member name and join time (CET) to User_List
    cet = pytz.timezone('Europe/Berlin')  # CET/CEST timezone
    join_time = datetime.now(cet).strftime("%Y-%m-%d %H:%M:%S CET")
    with open("User_List", "a", encoding="utf-8") as f:
        f.write(f"{member.name} - Joined: {join_time}\n")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if "shit" in message.content.lower():
        await message.delete()
        await message.channel.send(f"{message.author.mention} - dont use that word!")

    await bot.process_commands(message)

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {secret_role}")
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def remove(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} has had the {secret_role} removed")
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def dm(ctx, *, msg):
    await ctx.author.send(f"You said {msg}")

@bot.command()
async def reply(ctx):
    await ctx.reply("This is a reply to your message!")

@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(title="New Poll", description=question)
    poll_message = await ctx.send(embed=embed)
    await poll_message.add_reaction("👍")
    await poll_message.add_reaction("👎")

@bot.command()
@commands.has_role(secret_role)
async def secret(ctx):
    await ctx.send("Welcome to the club!")

@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You do not have permission to do that!")

bot.run(token, log_handler=handler, log_level=logging.DEBUG)