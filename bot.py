import discord
from discord.ext import commands
import csv
import os

# --- CONFIGURATION ---
TOKEN_FILE = 'token.txt'
ADMIN_FILE = 'admin.txt'
CSV_FILE = 'pairs.csv'
# ---------------------

try:
    with open(TOKEN_FILE, encoding='utf-8') as token_file:
        TOKEN = token_file.read().strip()
except FileNotFoundError as error:
    raise RuntimeError(f'Missing token file: {TOKEN_FILE}') from error

if not TOKEN:
    raise RuntimeError(f'Token file is empty: {TOKEN_FILE}')

try:
    with open(ADMIN_FILE, encoding='utf-8') as admin_file:
        ADMIN_ID = [int(line.strip()) for line in admin_file if line.strip()]
except FileNotFoundError as error:
    raise RuntimeError(f'Missing admin file: {ADMIN_FILE}') from error
except ValueError as error:
    raise RuntimeError(f'Admin file contains an invalid user ID: {ADMIN_FILE}') from error

if not ADMIN_ID:
    raise RuntimeError(f'Admin file is empty: {ADMIN_FILE}')

intents = discord.Intents.default()
intents.message_content = True  # Required to read message contents
bot = commands.Bot(command_prefix='$', intents=intents)
bot.remove_command('help')

# Dictionary to hold symmetric pairs: {user1_id: user2_id, user2_id: user1_id}
pairs = {}

def load_pairs():
    """Loads pairs from the CSV file into memory."""
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 2:
                    u1, u2 = int(row[0]), int(row[1])
                    pairs[u1] = u2
                    pairs[u2] = u1

def save_pairs():
    """Saves the current memory dictionary back to the CSV file."""
    written = set()
    with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for u1, u2 in pairs.items():
            if u1 not in written:
                writer.writerow([u1, u2])
                written.add(u1)
                written.add(u2)

# --- CHECKS ---
def is_admin(ctx):
    return ctx.author.id in ADMIN_ID

def save_admins():
    """Saves the current admin list to the local configuration file."""
    with open(ADMIN_FILE, mode='w', encoding='utf-8') as admin_file:
        admin_file.write('\n'.join(str(admin_id) for admin_id in ADMIN_ID) + '\n')

# --- COMMANDS ---
@bot.command()
@commands.check(is_admin)
@commands.dm_only()
async def help(ctx):
    """Lists all available commands and their usage."""
    commands_list = sorted(
        f"`{bot.command_prefix}{command.name}`: {command.help or 'No description available.'}"
        for command in bot.commands
    )
    await ctx.send("**Available commands:**\n" + "\n".join(commands_list))

@bot.command()
@commands.check(is_admin)
@commands.dm_only()
async def pair(ctx, user1_id: int, user2_id: int):
    """Admin command: Pairs two users together ($pair <user1_id> <user2_id>)"""
    if user1_id in pairs:
        await ctx.send(f"User {user1_id} is already paired with {pairs[user1_id]}. Unpair them first.")
        return
    if user2_id in pairs:
        await ctx.send(f"User {user2_id} is already paired with {pairs[user2_id]}. Unpair them first.")
        return

    # Assign pair in both directions
    pairs[user1_id] = user2_id
    pairs[user2_id] = user1_id
    save_pairs()
    
    await ctx.send(f"✅ Successfully paired `{user1_id}` with `{user2_id}`.")

@bot.command()
@commands.check(is_admin)
@commands.dm_only()
async def addadmin(ctx, user_id: int):
    """Admin command: Adds a user to the admin list ($addadmin <user_id>)"""
    if user_id in ADMIN_ID:
        await ctx.send(f"❌ User `{user_id}` is already an admin.")
        return

    ADMIN_ID.append(user_id)
    save_admins()
    await ctx.send(f"✅ Successfully added `{user_id}` as an admin.")

@bot.command()
@commands.check(is_admin)
@commands.dm_only()
async def removeadmin(ctx, user_id: int):
    """Admin command: Removes a user from the admin list ($removeadmin <user_id>)"""
    if user_id == ctx.author.id:
        await ctx.send("❌ You cannot remove yourself as an admin.")
        return
    if user_id not in ADMIN_ID:
        await ctx.send(f"❌ User `{user_id}` is not currently an admin.")
        return

    ADMIN_ID.remove(user_id)
    save_admins()
    await ctx.send(f"✅ Successfully removed `{user_id}` as an admin.")

@bot.command(name="listadmins", aliases=["admins"])
@commands.check(is_admin)
@commands.dm_only()
async def list_admins(ctx):
    """Admin command: Lists all admins ($listadmins)"""
    if not ADMIN_ID:
        await ctx.send("No admins are currently configured.")
        return

    admin_list = []
    for admin_id in ADMIN_ID:
        user = bot.get_user(admin_id)
        if not user:
            try:
                user = await bot.fetch_user(admin_id)
            except discord.NotFound:
                admin_list.append(f"• `Unknown User ({admin_id})`")
                continue
            except discord.HTTPException:
                admin_list.append(f"• `Error Fetching ({admin_id})`")
                continue

        admin_list.append(f"• `{user.name} ({admin_id})`")

    await ctx.send("**Current admins:**\n" + "\n".join(admin_list))

@bot.command()
@commands.check(is_admin)
@commands.dm_only()
async def unpair(ctx, user_id: int):
    """Admin command: Removes a pair involving the given user ($unpair <user_id>)"""
    if user_id not in pairs:
        await ctx.send(f"❌ User `{user_id}` is not currently in a pair.")
        return

    partner_id = pairs[user_id]
    
    # Remove from both sides
    del pairs[user_id]
    del pairs[partner_id]
    save_pairs()

    await ctx.send(f"✅ Successfully unpaired `{user_id}` and `{partner_id}`.")

@bot.command(name="list")
@commands.check(is_admin)
@commands.dm_only()
async def list_pairs(ctx):
    """Admin command: Lists all current user pairs with usernames ($list)"""
    if not pairs:
        await ctx.send("No pairs are currently set.")
        return

    # Send a temporary loading message since fetching users from Discord's API can take a second
    loading_msg = await ctx.send("⏳ Fetching usernames...")

    listed = set()
    message = "**Current Pairs:**\n"
    
    for u1, u2 in pairs.items():
        if u1 not in listed:
            # Helper function to get a user's name safely
            async def get_user_display(user_id):
                user = bot.get_user(user_id) # Try local cache first
                if not user:
                    try:
                        user = await bot.fetch_user(user_id) # Ask Discord API
                    except discord.NotFound:
                        return f"Unknown User ({user_id})"
                    except discord.HTTPException:
                        return f"Error Fetching ({user_id})"
                # Return the username and the ID for clarity
                return f"{user.name} ({user_id})"

            name1 = await get_user_display(u1)
            name2 = await get_user_display(u2)

            message += f"• `{name1}` ↔ `{name2}`\n"
            
            listed.add(u1)
            listed.add(u2)
    
    # Edit the loading message with the final list
    await loading_msg.edit(content=message)

# --- EVENTS ---
@bot.event
async def on_ready():
    load_pairs()
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Pairs loaded:', pairs)

@bot.event
async def on_message(message):
    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Process commands first so admin commands aren't treated as relayed messages
    await bot.process_commands(message)

    # Check if the message is in a DM and doesn't start with the command prefix
    if isinstance(message.channel, discord.DMChannel) and not message.content.startswith(bot.command_prefix):
        author_id = message.author.id
        
        # If the user is part of a pair, relay the message
        if author_id in pairs:
            target_id = pairs[author_id]
            
            try:
                # Fetch the target user object
                target_user = await bot.fetch_user(target_id)
                
                # Relay attachments if they sent images/files
                files = []
                for attachment in message.attachments:
                    files.append(await attachment.to_file())
                
                # Send the message to the paired user
                await target_user.send(content=message.content, files=files)
                
            except discord.Forbidden:
                # Triggers if the target user has blocked the bot or disabled DMs
                await message.channel.send("⚠️ Cannot send message. Your partner has DMs disabled.")
            except discord.NotFound:
                await message.channel.send("⚠️ Partner user account not found.")
            except Exception as e:
                await message.channel.send("⚠️ An error occurred while routing the message.")
                print(f"Relay Error: {e}")
        else:
            await message.channel.send("❌ You are not currently paired with anyone.")

# --- ERROR HANDLING ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You do not have permission to use this command.")
    elif isinstance(error, commands.PrivateMessageOnly):
        await ctx.send("❌ This command can only be used in Private Messages.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing arguments. Check the command syntax.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument. Please provide valid User IDs (numbers).")
    else:
        raise error

# Run the bot
bot.run(TOKEN)