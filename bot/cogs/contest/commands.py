import discord
from discord.ext import commands

from bot.cogs.contest.utils import get_logs_channel
from bot.core.error_embed import create_logs_embed

class ContestCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["ServerConfig"]

    @commands.hybrid_command(name="contest_submission_channel", description="Select submission channel")
    async def contest_submission_channel(self, ctx: commands.Context, *, channel: discord.TextChannel = None):
        await ctx.defer()
        logs_channel = await get_logs_channel(self.bot, guild_id=ctx.guild.id)
        if logs_channel:
            logs_embed = create_logs_embed(
                title="Submission channel set",
                description=f"Submission channel set to <#{channel.id}>" if channel else "Submission channel unset",
                color=discord.Color.green() if channel else discord.Color.red()
            )
            await logs_channel.send(embed=logs_embed)

        if channel is None:
            channel = ctx.channel

        try:
            await self.collection.update_one(
                {"_id": ctx.guild.id},
                {"$set": {"submission_channel": channel.id}},
                upsert=True)
            await ctx.send(f"<#{channel.id}> is set as submission channel")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.hybrid_command(name="contest_voting_channel", description="Select voting channel")
    async def contest_voting_channel(self, ctx: commands.Context, *, channel: discord.ForumChannel = None):
        await ctx.defer()
        if channel is None:
            channel = ctx.channel
        if not isinstance(channel, discord.ForumChannel):
            await ctx.send("Please select a valid forum channel for voting.")
            return
        try:
            await self.collection.update_one(
                {"_id": ctx.guild.id},
                {"$set": {"voting_channel": channel.id}},
                upsert=True
            )
            await ctx.send(f"<#{channel.id}> is set as voting channel")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.hybrid_command(name="contest_role", description="Select contest role")
    async def contest_role(self, ctx: commands.Context, *, role: discord.Role = None):
        await ctx.defer()
        if role is None:
            await ctx.send("Please specify a role.")
            return
        bot_member = ctx.guild.me
        server_config = await self.collection.find_one({"_id": ctx.guild.id})
        ann_id = server_config.get("contest_announcement_channel") if server_config else None
        announcement_channel = ctx.guild.get_channel(ann_id) if ann_id else None
        
        if announcement_channel:
            overwrites = {
                bot_member: discord.PermissionOverwrite(view_channel=True, manage_channels=True, send_messages=True, manage_threads=True, read_message_history=True),
                role: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False),
                ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
            }
            await announcement_channel.edit(overwrites=overwrites)

        try:
            await self.collection.update_one(
                {"_id": ctx.guild.id},
                {"$set": {"contest_role": role.id}},
                upsert=True)
            await ctx.send(f"{role.mention} is set as contest role")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.hybrid_command(name="contest_start_now", description="Force-start a contest cycle immediately")
    @commands.has_permissions(administrator=True)
    async def contest_start_now(self, ctx: commands.Context):
        await ctx.defer()
        try:
            from bot.cogs.contest.jobs import start_submissions
            await start_submissions()
            await ctx.send("🚀 **Contest Forced!** Submissions are now open.")
        except Exception as e:
            await ctx.send(f"❌ Error during start-up: {e}")

    @commands.hybrid_command(name="contest_vote_now", description="Force-start the voting phase immediately")
    @commands.has_permissions(administrator=True)
    async def contest_vote_now(self, ctx: commands.Context):
        await ctx.defer()
        try:
            from bot.cogs.contest.jobs import start_voting
            await start_voting()
            await ctx.send("🗳️ Submissions closed. Voting gallery is now live!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.hybrid_command(name="contest_winner_now", description="Force-end the contest and announce winner")
    @commands.has_permissions(administrator=True)
    async def contest_winner_now(self, ctx: commands.Context):
        await ctx.defer()
        try:
            from bot.cogs.contest.jobs import announce_winner
            await announce_winner()
            await ctx.send("🏆 Votes counted! Winner has been announced.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.hybrid_command(name="contest_create_channel", description="Create contest channel")
    async def contest_create_channel(self, ctx: commands.Context):
        await ctx.defer()
        guild = ctx.guild
        bot_member = guild.me
        server_config = await self.collection.find_one({"_id": guild.id})
        
        # Simplified logic for creating the category and channels
        contest_category = discord.utils.get(guild.categories, name="Contest") or await guild.create_category("Contest")
        
        async def create_chan(name, cls):
            existing = discord.utils.get(guild.channels, name=name)
            if existing: return existing
            if cls == discord.TextChannel:
                return await guild.create_text_channel(name, category=contest_category)
            return await guild.create_forum(name, category=contest_category)

        sub = await create_chan("contest-submit", discord.TextChannel)
        vote = await create_chan("contest-vote", discord.ForumChannel)
        ann = await create_chan("contest-announcement", discord.TextChannel)
        
        await self.collection.update_one(
            {"_id": guild.id},
            {"$set": {"submission_channel": sub.id, "voting_channel": vote.id, "contest_announcement_channel": ann.id}},
            upsert=True
        )
        await ctx.send("Contest channels are ready!")
