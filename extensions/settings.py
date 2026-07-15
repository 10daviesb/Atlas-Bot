import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Settings")

DB_PATH = "atlas.db"

# Extensions that must stay on
_PROTECTED = {"settings", "errorhandler"}


def _is_admin(ctx: lightbulb.Context) -> bool:
    return isinstance(ctx.member, hikari.Member) and bool(ctx.member.permissions & hikari.Permissions.ADMINISTRATOR)


def _all_command_names(bot: lightbulb.BotApp) -> list[str]:
    names = []
    for cmd in bot.slash_commands.values():
        if hasattr(cmd, "subcommands"):
            for child in cmd.subcommands.values():
                if hasattr(child, "subcommands"):
                    for grandchild in child.subcommands.values():
                        names.append(f"{cmd.name} {child.name} {grandchild.name}")
                else:
                    names.append(f"{cmd.name} {child.name}")
        else:
            names.append(cmd.name)
    return sorted(names)


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_extensions (
                guild_id  INTEGER NOT NULL,
                extension TEXT    NOT NULL,
                enabled   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, extension)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_commands (
                guild_id  INTEGER NOT NULL,
                command   TEXT    NOT NULL,
                enabled   INTEGER NOT NULL DEFAULT 1,
                role_id   INTEGER,
                PRIMARY KEY (guild_id, command)
            )
        """)
        await db.commit()
    logger.info("Settings DB initialized.")


# ── /config ───────────────────────────────────────────────────────────────────

@plugin.command()
@lightbulb.command("config", "Manage bot settings for this server.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def config_group(ctx: lightbulb.Context) -> None:
    pass


# ── /config extension ─────────────────────────────────────────────────────────

@config_group.child
@lightbulb.command("extension", "Enable or disable whole extensions.")
@lightbulb.implements(lightbulb.SlashSubGroup)
async def config_ext(ctx: lightbulb.Context) -> None:
    pass


@config_ext.child
@lightbulb.command("list", "Show all extensions and whether they're enabled.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ext_list(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT extension, enabled FROM guild_extensions WHERE guild_id = ?",
            (ctx.guild_id,),
        ) as cur:
            overrides = {row[0]: bool(row[1]) for row in await cur.fetchall()}

    plugins = sorted(
        p for p in ctx.bot.plugins if p not in ("Settings", "ErrorHandler")
    )
    lines = ["**Extensions**"]
    for name in plugins:
        key = name.lower()
        enabled = overrides.get(key, True)
        lines.append(f"{'✅' if enabled else '❌'} **{name}**")

    await ctx.respond("\n".join(lines))


@config_ext.child
@lightbulb.option("name", "Extension name, e.g. Moderation, Fun.", type=str)
@lightbulb.command("enable", "Enable an extension for this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ext_enable(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    name = ctx.options.name.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO guild_extensions (guild_id, extension, enabled) VALUES (?, ?, 1)
            ON CONFLICT(guild_id, extension) DO UPDATE SET enabled = 1
        """, (ctx.guild_id, name.lower()))
        await db.commit()
    await ctx.respond(f"✅ **{name}** extension enabled.")


@config_ext.child
@lightbulb.option("name", "Extension name, e.g. Moderation, Fun.", type=str)
@lightbulb.command("disable", "Disable an extension for this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ext_disable(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    name = ctx.options.name.strip()
    if name.lower() in _PROTECTED:
        await ctx.respond(f"❌ **{name}** cannot be disabled.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO guild_extensions (guild_id, extension, enabled) VALUES (?, ?, 0)
            ON CONFLICT(guild_id, extension) DO UPDATE SET enabled = 0
        """, (ctx.guild_id, name.lower()))
        await db.commit()
    await ctx.respond(f"✅ **{name}** extension disabled.")


# ── /config command ───────────────────────────────────────────────────────────

@config_group.child
@lightbulb.command("command", "Enable, disable, or role-restrict individual commands.")
@lightbulb.implements(lightbulb.SlashSubGroup)
async def config_cmd(ctx: lightbulb.Context) -> None:
    pass


@config_cmd.child
@lightbulb.command("list", "Show all commands with non-default settings.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cmd_list(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT command, enabled, role_id FROM guild_commands WHERE guild_id = ?",
            (ctx.guild_id,),
        ) as cur:
            configured = {row[0]: (bool(row[1]), row[2]) for row in await cur.fetchall()}

    all_cmds = _all_command_names(ctx.bot)
    lines = ["**Commands** (non-default settings only)"]
    for name in all_cmds:
        if name in configured:
            enabled, role_id = configured[name]
            tags = []
            if not enabled:
                tags.append("❌ disabled")
            if role_id:
                tags.append(f"🔒 <@&{role_id}>")
            if tags:
                lines.append(f"`/{name}` — {', '.join(tags)}")

    if len(lines) == 1:
        lines.append("*All commands are using defaults.*")

    await ctx.respond("\n".join(lines))


@config_cmd.child
@lightbulb.command("listall", "Show every available command.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cmd_listall(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    names = _all_command_names(ctx.bot)
    await ctx.respond("**All commands:**\n" + "\n".join(f"`/{n}`" for n in names))


@config_cmd.child
@lightbulb.option("name", "Full command name, e.g. 'kick' or 'automod spam'.", type=str)
@lightbulb.command("enable", "Re-enable a disabled command.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cmd_enable(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    name = ctx.options.name.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO guild_commands (guild_id, command, enabled) VALUES (?, ?, 1)
            ON CONFLICT(guild_id, command) DO UPDATE SET enabled = 1
        """, (ctx.guild_id, name))
        await db.commit()
    await ctx.respond(f"✅ `/{name}` enabled.")


@config_cmd.child
@lightbulb.option("name", "Full command name, e.g. 'kick' or 'automod spam'.", type=str)
@lightbulb.command("disable", "Disable a command in this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cmd_disable(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    name = ctx.options.name.strip().lower()
    if name.startswith("config"):
        await ctx.respond("❌ Config commands cannot be disabled.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO guild_commands (guild_id, command, enabled) VALUES (?, ?, 0)
            ON CONFLICT(guild_id, command) DO UPDATE SET enabled = 0
        """, (ctx.guild_id, name))
        await db.commit()
    await ctx.respond(f"✅ `/{name}` disabled.")


@config_cmd.child
@lightbulb.option("role", "Role required to run this command.", type=hikari.Role)
@lightbulb.option("name", "Full command name, e.g. 'kick' or 'automod spam'.", type=str)
@lightbulb.command("restrict", "Restrict a command to users with a specific role.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cmd_restrict(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    name = ctx.options.name.strip().lower()
    role: hikari.Role = ctx.options.role
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO guild_commands (guild_id, command, enabled, role_id) VALUES (?, ?, 1, ?)
            ON CONFLICT(guild_id, command) DO UPDATE SET role_id = excluded.role_id, enabled = 1
        """, (ctx.guild_id, name, role.id))
        await db.commit()
    await ctx.respond(f"✅ `/{name}` restricted to **{role.name}**.")
    logger.info(f"{ctx.author} restricted /{name} to role {role.name} in guild {ctx.guild_id}")


@config_cmd.child
@lightbulb.option("name", "Full command name, e.g. 'kick' or 'automod spam'.", type=str)
@lightbulb.command("unrestrict", "Remove the role restriction from a command.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def cmd_unrestrict(ctx: lightbulb.Context) -> None:
    if not _is_admin(ctx):
        await ctx.respond("❌ Administrator permission required.")
        return
    name = ctx.options.name.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE guild_commands SET role_id = NULL WHERE guild_id = ? AND command = ?",
            (ctx.guild_id, name),
        )
        await db.commit()
    await ctx.respond(f"✅ Role restriction removed from `/{name}`.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Settings extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Settings extension unloaded.")
