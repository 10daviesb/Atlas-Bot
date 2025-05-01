import lightbulb
import os
import logging
import hikari
import traceback

plugin = lightbulb.Plugin("Admin")

logger = logging.getLogger(__name__)

@plugin.command()
@lightbulb.command("reload", "Reload all extensions, including new ones.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def reload_command(ctx: lightbulb.Context) -> None:
    # Ensure ctx.author is a Member (has permissions)
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.ADMINISTRATOR:
        await ctx.respond("❌ You don't have permission to use this command.")
        return

    extensions = [f[:-3] for f in os.listdir("extensions") if f.endswith(".py")]
    
    loaded_extensions = []
    failed_extensions = []

    for ext in extensions:
        ext_path = f"extensions.{ext}"
        try:
            if ext_path in ctx.bot.extensions:
                ctx.bot.reload_extensions(ext_path)
            else:
                ctx.bot.load_extensions(ext_path)
            loaded_extensions.append(ext)
        except Exception as e:
            logger.error(f"Error loading {ext_path}:\n{traceback.format_exc()}")
            failed_extensions.append(ext)

    logger.info(f"Reloaded extensions successfully at {ctx.author.username}")
    response = f"✅ Reloaded/Loaded extensions: {', '.join(loaded_extensions)}"
    if failed_extensions:
        logger.error(f"Error during reload command execution: {ctx.author.username}")
        response += f"\n⚠️ Failed extensions: {', '.join(failed_extensions)}\nCheck logs for details."

    await ctx.respond(response)

def load(bot):
    bot.add_plugin(plugin)

def unload(bot):
    bot.remove_plugin(plugin)
