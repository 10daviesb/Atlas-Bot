import aiosqlite
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("CustomCommands")

DB_PATH = "atlas.db"

# guild_id -> {name: response}
_commands: dict[int, dict[str, str]] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_commands (
                guild_id INTEGER NOT NULL,
                name     TEXT    NOT NULL,
                response TEXT    NOT NULL,
                PRIMARY KEY (guild_id, name)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, name, response FROM custom_commands") as cur:
            for guild_id, name, response in await cur.fetchall():
                _commands.setdefault(guild_id, {})[name] = response
    logger.info(f"CustomCommands loaded: {sum(len(v) for v in _commands.values())} commands.")


@plugin.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    """Prefix-based invocation — requires MESSAGE_CONTENT privileged intent."""
    if event.author.is_bot or not event.content:
        return
    if not event.content.startswith(config.PREFIX):
        return
    name = event.content[len(config.PREFIX):].split()[0].lower()
    response = _commands.get(event.guild_id, {}).get(name)
    if response:
        await plugin.bot.rest.create_message(event.channel_id, response)


@plugin.command()
@lightbulb.option("name", "Command name to run.", type=str)
@lightbulb.command("cmd", "Run a custom server command.")
@lightbulb.implements(lightbulb.SlashCommand)
async def cmd(ctx: lightbulb.Context) -> None:
    name = ctx.options.name.strip().lower()
    response = _commands.get(ctx.guild_id, {}).get(name)
    if not response:
        cmds = sorted(_commands.get(ctx.guild_id, {}).keys())
        hint = f" Available: {', '.join(f'`{c}`' for c in cmds)}" if cmds else ""
        await ctx.respond(f"❌ No custom command named `{name}`.{hint}")
        return
    await ctx.respond(response)


@plugin.command()
@lightbulb.command("cc", "Manage custom commands.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def cc(ctx: lightbulb.Context) -> None:
    pass


@cc.child
@lightbulb.option("response", "What the bot should say.", type=str)
@lightbulb.option("name", "Command name (no spaces).", type=str)
@lightbulb.command("add", "Add or update a custom command.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cc_add(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    name = ctx.options.name.strip().lower().replace(" ", "-")
    response = ctx.options.response
    _commands.setdefault(ctx.guild_id, {})[name] = response
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO custom_commands (guild_id, name, response) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, name) DO UPDATE SET response = excluded.response
        """, (ctx.guild_id, name, response))
        await db.commit()
    await ctx.respond(f"✅ Custom command `{name}` saved. Run it with `/cmd {name}` or `{config.PREFIX}{name}`.")


@cc.child
@lightbulb.option("name", "Command name to remove.", type=str)
@lightbulb.command("remove", "Remove a custom command.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cc_remove(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    name = ctx.options.name.strip().lower()
    _commands.get(ctx.guild_id, {}).pop(name, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM custom_commands WHERE guild_id = ? AND name = ?", (ctx.guild_id, name))
        await db.commit()
    await ctx.respond(f"✅ Custom command `{name}` removed.")


@cc.child
@lightbulb.command("list", "List all custom commands in this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cc_list(ctx: lightbulb.Context) -> None:
    cmds = _commands.get(ctx.guild_id, {})
    if not cmds:
        await ctx.respond("📭 No custom commands set up. Use `/cc add` to create one.")
        return
    lines = ["**Custom Commands**"]
    for name in sorted(cmds):
        preview = cmds[name][:80] + ("…" if len(cmds[name]) > 80 else "")
        lines.append(f"`{name}` — {preview}")
    await ctx.respond("\n".join(lines))


def load(bot):
    bot.add_plugin(plugin)
    logger.info("CustomCommands extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("CustomCommands extension unloaded.")
