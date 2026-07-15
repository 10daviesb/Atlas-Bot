import asyncio
import logging
import time

import aiosqlite
import hikari
import lightbulb
from config import config
from errors import ExtensionDisabledError, CommandDisabledError, MissingCommandRoleError

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_logs.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)
BOT_START_TIME = time.time()

EXTENSIONS = [
    "extensions.errorhandler",
    "extensions.settings",
    "extensions.moderation",
    "extensions.utility",
    "extensions.info",
    "extensions.fun",
    "extensions.polls",
    "extensions.automod",
    "extensions.reactionroles",
    "extensions.reminders",
    "extensions.games",
    "extensions.auditlog",
    "extensions.starboard",
    "extensions.customcommands",
    "extensions.giveaways",
    "extensions.tickets",
    "extensions.economy",
    "extensions.afk",
    "extensions.suggestions",
    "extensions.autoroles",
    "extensions.temproles",
    "extensions.verification",
    "extensions.birthdays",
    "extensions.streamnotify",
    "extensions.shop",
    "extensions.counting",
    "extensions.bumper",
    "extensions.admin",
    "extensions.leveling",   # has should_load_hook checking config.ENABLE_LEVELING
    "extensions.music",      # has should_load_hook checking config.ENABLE_MUSIC
    "extensions.welcome",    # has should_load_hook checking config.ENABLE_WELCOME_MESSAGES
]


def _get_ext_name(ctx: lightbulb.Context) -> str | None:
    """Walk parent chain to find extension name from module path."""
    data = ctx.command._command_data
    while data is not None:
        ext = getattr(data, "extension", None)
        if ext:
            return ext.split(".")[-1]
        data = getattr(data, "parent", None)
    return None


def _full_cmd_name(ctx: lightbulb.Context) -> str:
    """Build full slash command name e.g. 'config extension enable'."""
    parts = []
    data = ctx.command._command_data
    while data is not None:
        parts.append(data.name)
        data = getattr(data, "parent", None)
    return " ".join(reversed(parts))


@lightbulb.hook(lightbulb.ExecutionSteps.CHECKS)
async def guild_settings_check(pl: lightbulb.ExecutionPipeline, ctx: lightbulb.Context) -> None:
    if not ctx.guild_id:
        return
    if ctx.member and ctx.member.permissions & hikari.Permissions.ADMINISTRATOR:
        return
    ext_name = _get_ext_name(ctx)
    if ext_name in ("settings", "errorhandler"):
        return
    cmd_name = _full_cmd_name(ctx)
    try:
        async with aiosqlite.connect("atlas.db") as db:
            if ext_name:
                async with db.execute(
                    "SELECT enabled FROM guild_extensions WHERE guild_id = ? AND extension = ?",
                    (ctx.guild_id, ext_name),
                ) as cur:
                    row = await cur.fetchone()
                if row and not row[0]:
                    pl.fail(ExtensionDisabledError(ext_name))
                    return
            async with db.execute(
                "SELECT enabled, role_id FROM guild_commands WHERE guild_id = ? AND command = ?",
                (ctx.guild_id, cmd_name),
            ) as cur:
                row = await cur.fetchone()
            if row:
                enabled, role_id = row
                if not enabled:
                    pl.fail(CommandDisabledError(cmd_name))
                    return
                if role_id and ctx.member and role_id not in ctx.member.role_ids:
                    pl.fail(MissingCommandRoleError(role_id))
    except (ExtensionDisabledError, CommandDisabledError, MissingCommandRoleError):
        raise
    except Exception:
        logger.exception("guild_settings_check DB error — failing open")


bot = hikari.GatewayBot(
    token=config.TOKEN,
    intents=(
        hikari.Intents.ALL_UNPRIVILEGED
        | hikari.Intents.GUILD_MEMBERS
        | hikari.Intents.MESSAGE_CONTENT
    ),
)

client = lightbulb.client_from_app(
    bot,
    default_enabled_guilds=[config.GUILD_ID] if config.GUILD_ID else (),
    hooks=[guild_settings_check],
)


@bot.listen(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    await client.load_extensions(*EXTENSIONS)
    await client.start()
    logger.info("AtlasBot started.")


if __name__ == "__main__":
    bot.run()
