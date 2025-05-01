import hikari
import lightbulb
import logging
import time
from bot import BOT_START_TIME

logger = logging.getLogger(__name__)
start_time = time.time()

# Create a plugin for utility commands
plugin = lightbulb.Plugin("Utility")

@plugin.command()
@lightbulb.command("ping", "Check if the bot is responsive.")
@lightbulb.implements(lightbulb.SlashCommand)
async def ping(ctx):
    latency = ctx.bot.heartbeat_latency * 1000  # Convert to milliseconds
    await ctx.respond(f"🏓 Pong! Latency: {latency:.2f}ms")
    logger.info(f"Ping command used by {ctx.author}")

@plugin.command()
async def uptime(ctx):
    current_time = time.time()
    uptime_seconds = int(current_time - BOT_START_TIME)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    await ctx.respond(f"Uptime: {hours}h {minutes}m {seconds}s")

    logger.info(f"Uptime command used by {ctx.author}")

@plugin.command()
@lightbulb.command("help", "List available commands.")
@lightbulb.implements(lightbulb.SlashCommand)
async def help_command(ctx):
    bot = ctx.bot
    help_message = "**Available Commands:**\n"

    for command in bot.slash_commands.values():  # Fix: Access command objects
        help_message += f"- `/{command.name}`: {command.description}\n"

    await ctx.respond(help_message)
    logger.info(f"Help command used by {ctx.author}")

@plugin.command()
@lightbulb.command("sync", "Force sync all bot commands.")
@lightbulb.implements(lightbulb.SlashCommand)
async def sync_commands(ctx: lightbulb.Context) -> None:
    await ctx.bot.sync_application_commands()
    await ctx.respond("✅ Commands synced!")

# Load the plugin into the bot
def load(bot):
    bot.add_plugin(plugin)
    logger.info("Utility extension loaded.")

def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Utility extension unloaded.")
