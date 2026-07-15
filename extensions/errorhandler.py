import traceback
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("ErrorHandler")


@plugin.listener(lightbulb.CommandErrorEvent)
async def on_command_error(event: lightbulb.CommandErrorEvent) -> None:
    error = event.exception.__cause__ or event.exception

    if isinstance(error, lightbulb.CommandNotFound):
        return

    if isinstance(error, lightbulb.NotEnoughArguments):
        await event.context.respond("❌ Missing required arguments.")
        return

    if isinstance(error, lightbulb.CheckFailure):
        await event.context.respond("❌ You don't have permission to use this command.")
        return

    if isinstance(error, lightbulb.CommandIsOnCooldown):
        await event.context.respond(f"⏳ This command is on cooldown. Try again in **{error.retry_after:.1f}s**.")
        return

    await event.context.respond("❌ An unexpected error occurred. It has been logged.")
    logger.exception(f"Unhandled error in '/{event.context.command.name}'", exc_info=error)

    if config.ERROR_LOG_CHANNEL:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        content = (
            f"**Error in `/{event.context.command.name}`** "
            f"— guild `{event.context.guild_id}` — user `{event.context.author}`\n"
            f"```py\n{tb[:1900]}\n```"
        )
        try:
            await plugin.bot.rest.create_message(config.ERROR_LOG_CHANNEL, content)
        except Exception:
            logger.exception("Failed to post error to ERROR_LOG_CHANNEL")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("ErrorHandler extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("ErrorHandler extension unloaded.")
