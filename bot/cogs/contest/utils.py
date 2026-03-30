import io
import aiohttp
import discord

# --- Existing Getters ---

async def get_submission_channel(bot, guild_id):
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if not config:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            print(f"Guild not found. {guild_id}")
            return None
    return guild.get_channel(config["submission_channel"]) if "submission_channel" in config else None


async def get_voting_channel(bot, guild_id):
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if not config:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            print(f"Guild not found. {guild_id}")
            return None
    return guild.get_channel(config["voting_channel"]) if "voting_channel" in config else None


async def get_contest_role(bot, guild_id):
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if not config:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            print(f"Guild not found. {guild_id}")
            return None
    return guild.get_role(config["contest_role"]) if "contest_role" in config else None


async def get_contest_announcement_channel(bot, guild_id):
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if not config:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            print(f"Guild not found. {guild_id}")
            return None
    return guild.get_channel(config["contest_announcement_channel"]) if "contest_announcement_channel" in config else None


async def get_contest_ping_role(bot, guild_id):
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if not config:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            print(f"Guild not found. {guild_id}")
            return None
    return guild.get_role(config["contest_ping_role"]) if "contest_ping_role" in config else None


async def get_logs_channel(bot, guild_id):
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if not config:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(guild_id)
        except discord.NotFound:
            print(f"Guild not found. {guild_id}")
            return None
    return guild.get_channel(config["contest_logs_channel"]) if "contest_logs_channel" in config else None


# --- File Downloader ---

async def get_discord_file_from_url(url: str, filename: str = None) -> discord.File:
    if filename is None:
        filename = url.split("/")[-1] or "file"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch file: HTTP {resp.status}")
            data = io.BytesIO(await resp.read())
            return discord.File(data, filename=filename)


# --- NEW ARCHIVE UTILS ---

async def get_contest_archive_channel(bot, guild_id: int):
    """Retrieves the Archive Channel object from the database."""
    config = await bot.db["ServerConfig"].find_one({"_id": guild_id})
    if config and "contest_archive_channel" in config:
        guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
        return guild.get_channel(config["contest_archive_channel"])
    return None


async def set_contest_archive_channel(bot, guild_id: int, channel_id: int):
    """Saves the Archive Channel ID to MongoDB."""
    await bot.db["ServerConfig"].update_one(
        {"_id": guild_id},
        {"$set": {"contest_archive_channel": channel_id}},
        upsert=True
    )
