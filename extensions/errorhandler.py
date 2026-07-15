import traceback
import lightbulb
import logging
from config import config
from errors import ExtensionDisabledError, CommandDisabledError, MissingCommandRoleError

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()


@loader.error_handler
async def on_error(exc: Exception, ctx: lightbulb.Context) -> bool:
    if isinstance(exc, ExtensionDisabledError):
        await ctx.respond(f"❌ The **{exc.extension}** extension is disabled in this server.")
        return True

    if isinstance(exc, CommandDisabledError):
        await ctx.respond(f"❌ The command **{exc.command}** is disabled in this server.")
        return True

    if isinstance(exc, MissingCommandRoleError):
        await ctx.respond(f"❌ You need the <@&{exc.role_id}> role to use this command.")
        return True

    # Log unhandled errors
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(f"Unhandled command error:\n{tb}")

    if config.DEBUG:
        await ctx.respond(f"❌ An error occurred:\n```py\n{tb[:1900]}```")
    else:
        await ctx.respond("❌ An unexpected error occurred. Please try again later.")

    return True
