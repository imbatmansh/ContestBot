import os
import shutil
from datetime import datetime
from pathlib import Path

import discord

from bot import GMT_TIMEZONE
from bot.cogs.contest.utils import (
    get_submission_channel, 
    get_contest_role, 
    get_voting_channel, 
    get_contest_announcement_channel, 
    get_contest_ping_role, 
    get_contest_archive_channel, 
    get_discord_file_from_url, 
    get_logs_channel
)
from bot.core.error_embed import create_logs_embed


class ContestJobs:
    def __init__(self, cog):
        self.cog = cog
        self.bot = self.cog.bot
        self.collection = self.bot.db["ServerConfig"]
        self.submissions_collection = self.bot.db["submissions"]

    async def schedule_job(self):
        """Sets the 'Alarm Clock' for every phase of the week."""
        scheduler = self.bot.scheduler
        async for config in self.collection.find({}):
            guild_id = config["_id"]

            # 1. Monday 02:00 - Open Submissions
            scheduler.add_job(self.open_submission_channel, "cron", day_of_week="mon", hour=2, minute=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})
            
            # 2. Friday 23:30 - Close Submissions
            scheduler.add_job(self.close_submission_channel, "cron", day_of_week="fri", hour=23, minute=30, second=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})
            
            # 3. Friday 23:59 - Move photos to Voting Forum
            scheduler.add_job(self.post_submission_to_forum, "cron", day_of_week="fri", hour=23, minute=59, second=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})
            
            # 4. Saturday 00:01 - Open Voting Channel
            scheduler.add_job(self.open_voting_channel, "cron", day_of_week="sat", hour=0, minute=1, second=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})
            
            # 5. Sunday 20:00 - Close Voting
            scheduler.add_job(self.close_voting_channel, "cron", day_of_week="sun", hour=20, minute=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})
            
            # 6. Sunday 21:00 - Announce Winner
            scheduler.add_job(self.announce_winner, "cron", day_of_week="sun", hour=21, minute=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})
            
            # 7. Sunday 23:00 - ARCHIVE & WIPE (Crucial for Monday start)
            scheduler.add_job(self.close_contest, "cron", day_of_week="sun", hour=23, minute=0, timezone=GMT_TIMEZONE, kwargs={"guild_id": guild_id})

    async def open_submission_channel(self, guild_id: int = None):
        submission_channel = await get_submission_channel(self.bot, guild_id=guild_id)
        member = await get_contest_role(self.bot, guild_id=guild_id)
        
        if submission_channel and member and isinstance(submission_channel, discord.TextChannel):
            overwrites = discord.PermissionOverwrite(send_messages=True, view_channel=True, read_message_history=False, attach_files=True)
            await submission_channel.set_permissions(member, overwrite=overwrites)
            
            announcement_channel = await get_contest_announcement_channel(self.bot, guild_id=guild_id)
            contest_ping_role = await get_contest_ping_role(self.bot, guild_id=guild_id)
            if announcement_channel:
                await announcement_channel.send(f"{contest_ping_role.mention if contest_ping_role else ''} Submissions are now OPEN! <#{submission_channel.id}>")

    async def close_submission_channel(self, guild_id: int = None):
        submission_channel = await get_submission_channel(self.bot, guild_id=guild_id)
        member = await get_contest_role(self.bot, guild_id=guild_id)
        if submission_channel and member:
            overwrites = discord.PermissionOverwrite(view_channel=False, send_messages=False)
            await submission_channel.set_permissions(member, overwrite=overwrites)

    async def post_submission_to_forum(self, guild_id: int = None):
        guild = self.bot.get_guild(guild_id)
        voting_channel = await get_voting_channel(self.bot, guild_id=guild_id)
        if not guild or not voting_channel: return

        current_month = datetime.now(GMT_TIMEZONE).strftime("%Y-%m")
        submissions = self.submissions_collection.find({"month": current_month, "guild_id": guild_id})

        async for entry in submissions:
            user = guild.get_member(entry["user_id"])
            if not user: continue
            
            file_path = os.path.normpath(entry["file_path"])
            if os.path.exists(file_path):
                file = discord.File(file_path, filename="submission.webp")
                thread = await voting_channel.create_thread(name=f"{user.display_name}'s Entry", content=" ", file=file)
                await thread.message.add_reaction("✅")
                await self.submissions_collection.update_one({"_id": entry["_id"]}, {"$set": {"thread_id": thread.message.id}})

    async def open_voting_channel(self, guild_id: int = None):
        voting_channel = await get_voting_channel(self.bot, guild_id=guild_id)
        member = await get_contest_role(self.bot, guild_id=guild_id)
        if voting_channel and member:
            overwrites = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
            await voting_channel.set_permissions(target=member, overwrite=overwrites)

    async def close_voting_channel(self, guild_id: int = None):
        voting_channel = await get_voting_channel(self.bot, guild_id=guild_id)
        member = await get_contest_role(self.bot, guild_id=guild_id)
        if voting_channel and member:
            overwrites = discord.PermissionOverwrite(view_channel=False, read_message_history=False)
            await voting_channel.set_permissions(target=member, overwrite=overwrites)

    async def announce_winner(self, guild_id: int = None):
        guild = self.bot.get_guild(guild_id)
        voting_channel = await get_voting_channel(self.bot, guild_id=guild_id)
        if not voting_channel: return

        top_votes = 0
        winners = []
        for thread in voting_channel.threads:
            async for msg in thread.history(limit=1):
                vote_count = sum(r.count for r in msg.reactions if str(r.emoji) == "✅")
                if vote_count > top_votes and vote_count > 0:
                    top_votes = vote_count
                    winners = [(msg.id, msg.attachments[0].url if msg.attachments else None)]
                elif vote_count == top_votes and vote_count > 0:
                    winners.append((msg.id, msg.attachments[0].url if msg.attachments else None))

        announcement_channel = await get_contest_announcement_channel(self.bot, guild_id=guild_id)
        if announcement_channel and winners:
            for thread_id, img_url in winners:
                winner_data = await self.submissions_collection.find_one({"thread_id": thread_id})
                if winner_data:
                    user = guild.get_member(winner_data["user_id"])
                    embed = discord.Embed(title="🏆 Winner Announced!", description=f"Congrats {user.mention} with {top_votes} votes!", color=0x00FF00)
                    if img_url: embed.set_image(url=img_url)
                    await announcement_channel.send(embed=embed)

    async def close_contest(self, guild_id: int = None):
        """Archives files to Discord AND local storage, then wipes DB."""
        guild = self.bot.get_guild(guild_id)
        voting_channel = await get_voting_channel(self.bot, guild_id=guild_id)
        art_archive_channel = await get_contest_archive_channel(self.bot, guild_id=guild_id)
        
        if not voting_channel or not art_archive_channel:
            print(f"Missing channels for archive: Voting={voting_channel}, Archive={art_archive_channel}")
            return

        # 1. Setup Local Archive Path for Railway Volume
        timestamp = datetime.now(GMT_TIMEZONE).strftime("%Y-Week-%W")
        local_archive_path = Path(f"bot/data/archive/{guild_id}/{timestamp}")
        local_archive_path.mkdir(parents=True, exist_ok=True)
        
        # 2. Process each thread in the voting channel
        for thread in voting_channel.threads:
            try:
                user_data = await self.submissions_collection.find_one({"thread_id": thread.id})
                if not user_data: continue
                
                user = guild.get_member(user_data["user_id"])
                if not user: continue

                # Get the image from the thread
                async for msg in thread.history(limit=1, oldest_first=True):
                    if msg.attachments:
                        attachment = msg.attachments[0]
                        # Create the DISCORD archive post
                        file = await get_discord_file_from_url(attachment.url, attachment.filename)
                        await art_archive_channel.send(
                            content=f"🎨 **Archive Entry**: {user.mention}\n📈 **Total Votes**: {sum(r.count for r in msg.reactions)}",
                            file=file
                        )

                # 3. Delete the thread after archiving to Discord
                await thread.delete()
            except Exception as e:
                print(f"Error archiving thread {thread.name}: {e}")

        # 4. Move local files to the Archive Volume
        submission_folder = Path(f"bot/data/submissions/{guild_id}")
        if submission_folder.exists():
            for file_item in submission_folder.iterdir():
                try:
                    shutil.move(str(file_item), str(local_archive_path / file_item.name))
                except Exception as e:
                    print(f"Local move error: {e}")

        # 5. FINAL STEP: Wipe the DB so Monday is fresh
        await self.submissions_collection.delete_many({"guild_id": guild_id})
        
        logs_channel = await get_logs_channel(self.bot, guild_id=guild_id)
        if logs_channel:
            await logs_channel.send(embed=create_logs_embed(
                title="Weekly Archive Success", 
                description="Contest data has been moved to the archive channel and local storage wiped.", 
                color=discord.Color.green()
            ))
