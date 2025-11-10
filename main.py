import discord
from discord.ext import commands, tasks
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import os
from datetime import datetime
import pytz
import asyncio

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = RotatingFileHandler(filename='discord.log', encoding='utf-8', mode='a', maxBytes=10*1024*1024, backupCount=5)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

roles = ["Admin","Tech Support","Calculo","Electronica Digital","Algebra","ICO","Progrmacion","Trusted"]

secret_role = "trusted"

def get_role_case_insensitive(guild: discord.Guild, name: str):
    """Return the role whose name matches case-insensitively, or None."""
    return discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)

def bot_has_permission(guild: discord.Guild, permission: str) -> bool:
    """Check if the bot has a specific guild-level permission."""
    me = guild.me if guild and guild.me else None
    if not me:
        return False
    perms = me.guild_permissions
    return getattr(perms, permission, False)

def get_users_from_list():
    """Read existing user IDs from User_List file."""
    user_ids = set()
    try:
        with open("User_List", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # New format: ID|DisplayName|Timestamp or ID|DisplayName - Joined: Timestamp
                if "|" in line:
                    user_id_str = line.split("|")[0].strip()
                    try:
                        user_id = int(user_id_str)
                        user_ids.add(user_id)
                    except ValueError:
                        continue
                elif line.startswith("ID:"):
                    try:
                        user_id = int(line.split("ID:")[1].split()[0])
                        user_ids.add(user_id)
                    except (ValueError, IndexError):
                        continue
    except FileNotFoundError:
        pass
    return user_ids

async def sync_users_to_list():
    """Check all members on server and add any missing ones to User_List."""
    cet = pytz.timezone('Europe/Berlin')
    current_time = datetime.now(cet).strftime("%Y-%m-%d %H:%M:%S CET")
    existing_user_ids = get_users_from_list()
    
    # Get all members from all guilds
    missing_members = []
    for guild in bot.guilds:
        for member in guild.members:
            if not member.bot and member.id not in existing_user_ids:  # Exclude bots and existing users
                missing_members.append(member)
    
    # Add missing members to the list
    if missing_members:
        with open("User_List", "a", encoding="utf-8") as f:
            for member in sorted(missing_members, key=lambda m: m.id):
                f.write(f"{member.id}|{member.display_name}|{current_time}\n")
        print(f"Added {len(missing_members)} missing member(s) to User_List")
    return len(missing_members)

@tasks.loop(hours=1)
async def hourly_sync():
    """Sync users every hour."""
    await sync_users_to_list()

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")
    await sync_users_to_list()
    hourly_sync.start()

@bot.event
async def on_member_remove(member):
    # Remove member by ID from User_List
    try:
        with open("User_List", "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open("User_List", "w", encoding="utf-8") as f:
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    f.write(line)
                    continue
                # Check if line contains member.id (handles both new format ID|DisplayName|Timestamp and old formats)
                if "|" in line_stripped:
                    # Extract ID from format: ID|DisplayName|Timestamp
                    try:
                        line_id = int(line_stripped.split("|")[0].strip())
                        if line_id == member.id:
                            continue  # Skip this line (member being removed)
                    except (ValueError, IndexError):
                        pass
                f.write(line)
    except FileNotFoundError:
        pass


@bot.event
async def on_member_join(member: discord.Member):
    real_name = "-" 
    try:
        await member.send(f"Welcome to the server, {member.display_name}! 🎉")
        await member.send("What is your actual name? Reply here within 2 minutes.")

        def check(m: discord.Message):
            return m.author == member and isinstance(m.channel, discord.DMChannel)

        # wait_for with a sensible timeout
        msg = await bot.wait_for("message", check=check, timeout=120)
        # sanitize pipe to keep your `|`-separated file format
        real_name = msg.content.replace("|", "¦").strip() or "-"
        await member.send(f"Thanks, {real_name}! Your name has been noted.")
        # Set their nickname on the server
        nickname = real_name if real_name != "-" else None
        if nickname and bot_has_permission(member.guild, "manage_nicknames"):
            nickname = nickname[:32]  # Discord limit
            try:
                await member.edit(nick=nickname, reason="Provided real name to welcome DM")
            except discord.Forbidden:
                await member.send("I couldn't change your server nickname due to missing permissions.")
            except discord.HTTPException:
                await member.send("There was an error changing your nickname, but I saved your name.")
        elif nickname:
            await member.send("I don't have permission to change nicknames right now; please ask a moderator.")

        # Assign Trusted role after they provide their name
        role = get_role_case_insensitive(member.guild, secret_role)
        if role and bot_has_permission(member.guild, "manage_roles"):
            await member.add_roles(role, reason="Assigned after providing name")
            system_channel = member.guild.system_channel
            if system_channel:
                await system_channel.send(f"{member.mention} has been assigned to {secret_role}")
        elif role:
            await member.send("I couldn't assign you the trusted role because I am missing permissions. Please contact a moderator.")
    except discord.Forbidden:
        pass
    except asyncio.TimeoutError:
        try:
            await member.send("No worries—if you want me to note your name later, just DM me.")
        except discord.Forbidden:
            pass

    tz = pytz.timezone("Europe/Berlin")  # CET/CEST
    join_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    display_name_sanitized = member.display_name.replace("|", "¦").strip() or "-"
    try:
        with open("User_List", "a", encoding="utf-8") as f:
            # Format: ID|DisplayName|RealName|Timestamp
            f.write(f"{member.id}|{display_name_sanitized}|{real_name}|{join_time}\n")
    except Exception as e:
        print(f"Failed to write User_List: {e}")


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
    role = get_role_case_insensitive(ctx.guild, secret_role)
    if role and bot_has_permission(ctx.guild, "manage_roles"):
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {secret_role}")
    elif role:
        await ctx.send("I can't assign that role right now; please check my permissions.")
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def remove(ctx):
    role = get_role_case_insensitive(ctx.guild, secret_role)
    if role and bot_has_permission(ctx.guild, "manage_roles"):
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} has had the {secret_role} removed")
    elif role:
        await ctx.send("I can't remove that role right now; please check my permissions.")
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

@bot.command(name="update_user_list")
@commands.has_role("test dev")
async def update_user_list(ctx):
    async with ctx.typing():
        added = await sync_users_to_list()
    await ctx.send(f"User_List updated. Added {added} new member(s).")

@update_user_list.error
async def update_user_list_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You do not have permission to update the User_List.")
    else:
        await ctx.send("An error occurred while updating the User_List.")

bot.run(token, log_handler=handler, log_level=logging.DEBUG)