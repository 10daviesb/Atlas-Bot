import aiosqlite
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {trigger -> response}
_commands: dict[int, dict[str, str]] = {}

PREFIX = getattr(config, "PREFIX", "!")


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_commands (
                guild_id INTEGER NOT NULL,
                trigger  TEXT    NOT NULL,
                response TEXT    NOT NULL,
                PRIMARY KEY (guild_id, trigger)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, trigger, response FROM custom_commands") as cur:
            for guild_id, trigger, response in await cur.fetchall():
                _commands.setdefault(guild_id, {})[trigger.lower()] = response
    logger.info(f"CustomCommands loaded: {sum(len(v) for v in _commands.values())} commands.")


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or not event.content or _rest is None:
        return
    content = event.content.strip()
    if not content.startswith(PREFIX):
        return
    trigger = content[len(PREFIX):].split()[0].lower()
    guild_cmds = _commands.get(event.guild_id, {})
    response = guild_cmds.get(trigger)
    if response:
        try:
            await _rest.create_message(event.channel_id, response)
        except Exception as e:
            logger.warning(f"CustomCommand response failed: {e}")


# /cc group for managing custom commands
cc_group = lightbulb.Group("cc", "Manage custom text commands.")


@cc_group.register
class CCAdd(lightbulb.SlashCommand, name="add", description="Add a custom command."):
    trigger = lightbulb.string("trigger", "The command trigger (without prefix).")
    response = lightbulb.string("response", "The response text.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        trigger = self.trigger.lower().strip()
        response = self.response
        _commands.setdefault(ctx.guild_id, {})[trigger] = response
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO custom_commands (guild_id, trigger, response) VALUES (?, ?, ?)
                ON CONFLICT(guild_id, trigger) DO UPDATE SET response = excluded.response
            """, (ctx.guild_id, trigger, response))
            await db.commit()
        await ctx.respond(f"✅ Custom command `{PREFIX}{trigger}` created.")


@cc_group.register
class CCRemove(lightbulb.SlashCommand, name="remove", description="Remove a custom command."):
    trigger = lightbulb.string("trigger", "The command trigger to remove.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        trigger = self.trigger.lower().strip()
        guild_cmds = _commands.get(ctx.guild_id, {})
        if trigger not in guild_cmds:
            await ctx.respond(f"⚠️ No custom command `{PREFIX}{trigger}` found.")
            return
        del guild_cmds[trigger]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM custom_commands WHERE guild_id = ? AND trigger = ?", (ctx.guild_id, trigger))
            await db.commit()
        await ctx.respond(f"✅ Custom command `{PREFIX}{trigger}` removed.")


@cc_group.register
class CCList(lightbulb.SlashCommand, name="list", description="List all custom commands."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        guild_cmds = _commands.get(ctx.guild_id, {})
        if not guild_cmds:
            await ctx.respond("ℹ️ No custom commands set for this server.")
            return
        lines = [f"`{PREFIX}{t}` → {r[:60]}" for t, r in list(guild_cmds.items())[:25]]
        await ctx.respond("**Custom Commands:**\n" + "\n".join(lines))


loader.command(cc_group)
