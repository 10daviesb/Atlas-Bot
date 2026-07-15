import os
import hikari
import lightbulb
import logging
import time
import aiosqlite
from config import config
from errors import ExtensionDisabledError, CommandDisabledError, MissingCommandRoleError

# Set up logging
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,  # Dynamically adjust logging level
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_logs.log", mode='a'),
    ]
)

BOT_START_TIME = time.time()
logger = logging.getLogger(__name__)

# Bot initialization
bot = lightbulb.BotApp(
    token=config.TOKEN,
    prefix=config.PREFIX,
    intents=hikari.Intents.ALL_UNPRIVILEGED,
)

logger.info("Starting AtlasBot...")


def _full_cmd_name(ctx: lightbulb.Context) -> str:
    parts = [ctx.command.name]
    node = ctx.command
    while True:
        parent = getattr(node, "parent", None)
        if parent is None or not hasattr(parent, "name"):
            break
        if not isinstance(parent, (lightbulb.SlashCommandGroup, lightbulb.SlashSubGroup)):
            break
        parts.insert(0, parent.name)
        node = parent
    return " ".join(parts)


@lightbulb.Check
async def guild_settings_check(ctx: lightbulb.Context) -> bool:
    if not ctx.guild_id:
        return True
    if ctx.member and ctx.member.permissions & hikari.Permissions.ADMINISTRATOR:
        return True
    if ctx.command.plugin and ctx.command.plugin.name in ("Settings", "ErrorHandler"):
        return True

    cmd_name = _full_cmd_name(ctx)
    plugin_name = ctx.command.plugin.name.lower() if ctx.command.plugin else None

    try:
        async with aiosqlite.connect("atlas.db") as db:
            if plugin_name:
                async with db.execute(
                    "SELECT enabled FROM guild_extensions WHERE guild_id = ? AND extension = ?",
                    (ctx.guild_id, plugin_name),
                ) as cur:
                    row = await cur.fetchone()
                    if row and not row[0]:
                        raise ExtensionDisabledError(plugin_name)

            async with db.execute(
                "SELECT enabled, role_id FROM guild_commands WHERE guild_id = ? AND command = ?",
                (ctx.guild_id, cmd_name),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    enabled, role_id = row
                    if not enabled:
                        raise CommandDisabledError(cmd_name)
                    if role_id and role_id not in (ctx.member.role_ids if ctx.member else []):
                        raise MissingCommandRoleError(role_id)
    except (ExtensionDisabledError, CommandDisabledError, MissingCommandRoleError):
        raise
    except Exception:
        logger.exception("guild_settings_check DB error — failing open")

    return True


bot.add_checks(guild_settings_check)

# Load extensions dynamically with error handling
def load_extensions():
    for file in os.listdir("extensions"):
        if file.endswith(".py"):
            ext_name = f"extensions.{file[:-3]}"
            try:
                bot.load_extensions(ext_name)
                logger.info(f"Loaded extension: {ext_name}")
            except Exception as e:
                logger.exception(f"Failed to load extension {ext_name}")

load_extensions()

@bot.listen(hikari.StartedEvent)
async def on_starting(event: hikari.StartedEvent) -> None:
    await bot.rest.fetch_application()  # Ensures bot fetches latest command state
    await bot.sync_application_commands()
    print("✅ Synced application commands.")

# Run the bot
if __name__ == "__main__":
    bot.run()