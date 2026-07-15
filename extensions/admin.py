import logging
import hikari
import lightbulb

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()


@loader.command
class Reload(lightbulb.SlashCommand, name="reload", description="Reload all bot extensions."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need Administrator permission to use this command.")
            return

        await ctx.respond(
            "🔄 Reloading extensions at runtime is not supported in v3. "
            "Please restart the bot to apply changes."
        )
        logger.info(f"Reload command used by {ctx.user}")
