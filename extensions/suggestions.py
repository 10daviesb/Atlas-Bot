import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {channel_id, review_channel_id}
_suggest_config: dict[int, dict] = {}


async def _post_suggestion(guild_id: int, user: hikari.User, content: str) -> None:
    cfg = _suggest_config.get(guild_id)
    if not cfg or _rest is None:
        return
    channel_id = cfg["channel_id"]
    embed = hikari.Embed(
        title="New Suggestion",
        description=content,
        color=0x5865F2,
    )
    embed.set_author(name=user.username, icon=user.avatar_url or user.default_avatar_url)
    embed.set_footer(text=f"User ID: {user.id}")
    msg = await _rest.create_message(channel_id, embed=embed)
    await _rest.add_reaction(channel_id, msg.id, "👍")
    await _rest.add_reaction(channel_id, msg.id, "👎")

    # Save to DB
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO suggestions (guild_id, user_id, message_id, content, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (guild_id, user.id, msg.id, content))
        await db.commit()


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_config (
                guild_id        INTEGER PRIMARY KEY,
                channel_id      INTEGER NOT NULL,
                review_channel  INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                message_id INTEGER,
                content    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, review_channel FROM suggestion_config") as cur:
            for guild_id, channel_id, review_channel in await cur.fetchall():
                _suggest_config[guild_id] = {"channel_id": channel_id, "review_channel": review_channel}
    logger.info("Suggestions loaded.")


@loader.command
class SuggestionSetup(
    lightbulb.SlashCommand,
    name="suggestionsetup",
    description="Configure the suggestion system.",
):
    channel = lightbulb.channel("channel", "Channel where suggestions will be posted.")
    review_channel = lightbulb.channel("review_channel", "Channel for reviewing suggestions (optional).", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        ch = self.channel
        rev = self.review_channel
        _suggest_config[ctx.guild_id] = {
            "channel_id": ch.id,
            "review_channel": rev.id if rev else None,
        }
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO suggestion_config (guild_id, channel_id, review_channel) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, review_channel = excluded.review_channel
            """, (ctx.guild_id, ch.id, rev.id if rev else None))
            await db.commit()
        await ctx.respond(f"✅ Suggestion channel set to {ch.mention}.")


@loader.command
class Suggest(lightbulb.SlashCommand, name="suggest", description="Submit a suggestion."):
    content = lightbulb.string("content", "Your suggestion.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.guild_id not in _suggest_config:
            await ctx.respond("❌ Suggestions are not set up for this server.")
            return
        await _post_suggestion(ctx.guild_id, ctx.user, self.content)
        await ctx.respond("✅ Your suggestion has been submitted!", flags=hikari.MessageFlag.EPHEMERAL)


# /suggestion review group
suggestion_group = lightbulb.Group("suggestion", "Manage suggestions (moderators only).")


@suggestion_group.register
class SuggestionApprove(lightbulb.SlashCommand, name="approve", description="Approve a suggestion."):
    suggestion_id = lightbulb.integer("suggestion_id", "Suggestion ID to approve.")
    reason = lightbulb.string("reason", "Reason for approval.", default="Approved by moderator.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, user_id, message_id, content FROM suggestions WHERE id = ? AND guild_id = ?",
                (self.suggestion_id, ctx.guild_id)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await ctx.respond("❌ Suggestion not found.")
                return
            gid, user_id, message_id, content = row
            await db.execute("UPDATE suggestions SET status = 'approved' WHERE id = ?", (self.suggestion_id,))
            await db.commit()

        cfg = _suggest_config.get(ctx.guild_id)
        if cfg and message_id and _rest:
            try:
                embed = hikari.Embed(
                    title="✅ Suggestion Approved",
                    description=content,
                    color=0x00FF00,
                )
                embed.add_field("Reason", self.reason, inline=False)
                embed.set_footer(text=f"Approved by {ctx.user.username}")
                await _rest.edit_message(cfg["channel_id"], message_id, embed=embed)
            except Exception as e:
                logger.warning(f"Suggestion approve edit failed: {e}")

        await ctx.respond(f"✅ Suggestion #{self.suggestion_id} approved.")


@suggestion_group.register
class SuggestionDeny(lightbulb.SlashCommand, name="deny", description="Deny a suggestion."):
    suggestion_id = lightbulb.integer("suggestion_id", "Suggestion ID to deny.")
    reason = lightbulb.string("reason", "Reason for denial.", default="Denied by moderator.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, user_id, message_id, content FROM suggestions WHERE id = ? AND guild_id = ?",
                (self.suggestion_id, ctx.guild_id)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await ctx.respond("❌ Suggestion not found.")
                return
            gid, user_id, message_id, content = row
            await db.execute("UPDATE suggestions SET status = 'denied' WHERE id = ?", (self.suggestion_id,))
            await db.commit()

        cfg = _suggest_config.get(ctx.guild_id)
        if cfg and message_id and _rest:
            try:
                embed = hikari.Embed(
                    title="❌ Suggestion Denied",
                    description=content,
                    color=0xFF0000,
                )
                embed.add_field("Reason", self.reason, inline=False)
                embed.set_footer(text=f"Denied by {ctx.user.username}")
                await _rest.edit_message(cfg["channel_id"], message_id, embed=embed)
            except Exception as e:
                logger.warning(f"Suggestion deny edit failed: {e}")

        await ctx.respond(f"✅ Suggestion #{self.suggestion_id} denied.")


loader.command(suggestion_group)
