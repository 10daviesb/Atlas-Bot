import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"

# Known extension names (updated from EXTENSIONS list in bot.py)
KNOWN_EXTENSIONS = [
    "errorhandler", "settings", "moderation", "utility", "info", "fun",
    "polls", "automod", "reactionroles", "reminders", "games", "auditlog",
    "starboard", "customcommands", "giveaways", "tickets", "economy", "afk",
    "suggestions", "autoroles", "temproles", "verification", "birthdays",
    "streamnotify", "shop", "counting", "bumper", "admin", "leveling",
    "music", "welcome",
]


async def _ensure_tables() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_extensions (
                guild_id  INTEGER NOT NULL,
                extension TEXT    NOT NULL,
                enabled   INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, extension)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_commands (
                guild_id INTEGER NOT NULL,
                command  TEXT    NOT NULL,
                enabled  INTEGER NOT NULL DEFAULT 1,
                role_id  INTEGER,
                PRIMARY KEY (guild_id, command)
            )
        """)
        await db.commit()


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    await _ensure_tables()
    logger.info("Settings DB initialized.")


# /config group (3-level)
config_group = lightbulb.Group("config", "Configure bot settings for this server.")

# --- /config extension subgroup ---
ext_subgroup = config_group.subgroup("extension", "Enable/disable extensions.")


@ext_subgroup.register
class ExtEnable(lightbulb.SlashCommand, name="enable", description="Enable an extension."):
    extension = lightbulb.string("extension", "Extension name to enable.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return
        ext = self.extension.lower()
        if ext not in KNOWN_EXTENSIONS:
            await ctx.respond(f"❌ Unknown extension `{ext}`. Known: {', '.join(KNOWN_EXTENSIONS)}")
            return
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO guild_extensions (guild_id, extension, enabled) VALUES (?, ?, 1)
                ON CONFLICT(guild_id, extension) DO UPDATE SET enabled = 1
            """, (ctx.guild_id, ext))
            await db.commit()
        await ctx.respond(f"✅ Extension `{ext}` enabled.")


@ext_subgroup.register
class ExtDisable(lightbulb.SlashCommand, name="disable", description="Disable an extension."):
    extension = lightbulb.string("extension", "Extension name to disable.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return
        ext = self.extension.lower()
        if ext in ("settings", "errorhandler"):
            await ctx.respond("❌ You cannot disable core extensions.")
            return
        if ext not in KNOWN_EXTENSIONS:
            await ctx.respond(f"❌ Unknown extension `{ext}`.")
            return
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO guild_extensions (guild_id, extension, enabled) VALUES (?, ?, 0)
                ON CONFLICT(guild_id, extension) DO UPDATE SET enabled = 0
            """, (ctx.guild_id, ext))
            await db.commit()
        await ctx.respond(f"✅ Extension `{ext}` disabled.")


@ext_subgroup.register
class ExtList(lightbulb.SlashCommand, name="list", description="List all extensions and their status."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT extension, enabled FROM guild_extensions WHERE guild_id = ?",
                (ctx.guild_id,)
            ) as cur:
                rows = {row[0]: bool(row[1]) for row in await cur.fetchall()}

        lines = []
        for ext in KNOWN_EXTENSIONS:
            enabled = rows.get(ext, True)
            status = "✅" if enabled else "❌"
            lines.append(f"{status} `{ext}`")

        embed = hikari.Embed(title="Extension Status", description="\n".join(lines), color=0x5865F2)
        await ctx.respond(embed=embed)


# --- /config command subgroup ---
cmd_subgroup = config_group.subgroup("command", "Enable/disable commands or restrict them to a role.")


@cmd_subgroup.register
class CmdEnable(lightbulb.SlashCommand, name="enable", description="Enable a command."):
    command = lightbulb.string("command", "Full command name (e.g. 'ban' or 'config extension enable').")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return
        cmd = self.command.lower().strip()
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO guild_commands (guild_id, command, enabled, role_id) VALUES (?, ?, 1, NULL)
                ON CONFLICT(guild_id, command) DO UPDATE SET enabled = 1
            """, (ctx.guild_id, cmd))
            await db.commit()
        await ctx.respond(f"✅ Command `{cmd}` enabled.")


@cmd_subgroup.register
class CmdDisable(lightbulb.SlashCommand, name="disable", description="Disable a command."):
    command = lightbulb.string("command", "Full command name.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return
        cmd = self.command.lower().strip()
        if cmd.startswith("config"):
            await ctx.respond("❌ You cannot disable config commands.")
            return
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO guild_commands (guild_id, command, enabled, role_id) VALUES (?, ?, 0, NULL)
                ON CONFLICT(guild_id, command) DO UPDATE SET enabled = 0
            """, (ctx.guild_id, cmd))
            await db.commit()
        await ctx.respond(f"✅ Command `{cmd}` disabled.")


@cmd_subgroup.register
class CmdRole(lightbulb.SlashCommand, name="role", description="Restrict a command to a specific role."):
    command = lightbulb.string("command", "Full command name.")
    role = lightbulb.role("role", "Role required to use this command.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return
        cmd = self.command.lower().strip()
        role = self.role
        role_id = role.id if role else None
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO guild_commands (guild_id, command, enabled, role_id) VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, command) DO UPDATE SET role_id = excluded.role_id
            """, (ctx.guild_id, cmd, role_id))
            await db.commit()
        if role:
            await ctx.respond(f"✅ Command `{cmd}` restricted to {role.mention}.")
        else:
            await ctx.respond(f"✅ Role restriction for `{cmd}` cleared.")


@cmd_subgroup.register
class CmdList(lightbulb.SlashCommand, name="list", description="List command overrides for this server."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await _ensure_tables()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT command, enabled, role_id FROM guild_commands WHERE guild_id = ? ORDER BY command",
                (ctx.guild_id,)
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.respond("ℹ️ No command overrides configured.")
            return

        lines = []
        for cmd, enabled, role_id in rows:
            status = "✅" if enabled else "❌"
            role_str = f" (role: <@&{role_id}>)" if role_id else ""
            lines.append(f"{status} `{cmd}`{role_str}")

        embed = hikari.Embed(title="Command Overrides", description="\n".join(lines[:25]), color=0x5865F2)
        await ctx.respond(embed=embed)


loader.command(config_group)
