import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Welcome")

# In-memory store: guild_id -> channel_id
# A real deployment would persist this in a DB (config.DB_URI)
_welcome_channels: dict[int, int] = {}


@plugin.listener(hikari.MemberCreateEvent)
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    channel_id = _welcome_channels.get(event.guild_id)
    if not channel_id:
        return
    member = event.member
    try:
        await plugin.bot.rest.create_message(
            channel_id,
            f"👋 Welcome to the server, {member.mention}! We're glad to have you here.",
        )
        logger.info(f"Sent welcome message for {member} in guild {event.guild_id}")
    except Exception as e:
        logger.warning(f"Failed to send welcome message: {e}")


@plugin.command()
@lightbulb.option("channel", "The channel to send welcome messages in.", type=hikari.TextableGuildChannel)
@lightbulb.command("setwelcome", "Set the channel for welcome messages.")
@lightbulb.implements(lightbulb.SlashCommand)
async def set_welcome(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission to use this command.")
        return
    channel = ctx.options.channel
    _welcome_channels[ctx.guild_id] = channel.id
    await ctx.respond(f"✅ Welcome messages will be sent in {channel.mention}.")
    logger.info(f"{ctx.author} set welcome channel to #{channel.name} in guild {ctx.guild_id}")


@plugin.command()
@lightbulb.command("clearwelcome", "Disable welcome messages for this server.")
@lightbulb.implements(lightbulb.SlashCommand)
async def clear_welcome(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission to use this command.")
        return
    _welcome_channels.pop(ctx.guild_id, None)
    await ctx.respond("✅ Welcome messages have been disabled.")
    logger.info(f"{ctx.author} disabled welcome messages in guild {ctx.guild_id}")


def load(bot):
    if config.ENABLE_WELCOME_MESSAGES:
        bot.add_plugin(plugin)
        logger.info("Welcome extension loaded.")
    else:
        logger.info("Welcome extension skipped (ENABLE_WELCOME_MESSAGES=False).")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Welcome extension unloaded.")
