import datetime
import lightbulb
import hikari
import logging

logger = logging.getLogger(__name__)

# Create a moderation plugin
plugin = lightbulb.Plugin("Moderation")

# Kick Command
@plugin.command()
@lightbulb.option("member", "The user to kick.", type=hikari.Member)
@lightbulb.command("kick", "Kicks a user from the server.")
@lightbulb.implements(lightbulb.SlashCommand)
async def kick(ctx):
    member = ctx.options.member
    guild = ctx.get_guild()

    if not guild or not member:
        await ctx.respond("❌ Invalid member or guild.")
        return

    try:
        await ctx.bot.rest.kick_member(guild, member)
        await ctx.respond(f"✅ {member} has been kicked.")
        logger.info(f"{ctx.author} kicked {member}")
    except Exception as e:
        await ctx.respond(f"❌ Failed to kick {member}.")
        logger.warning(f"Failed to kick {member}: {e}")

# Ban Command
@plugin.command()
@lightbulb.option("member", "The user to ban.", type=hikari.Member)
@lightbulb.command("ban", "Bans a user from the server.")
@lightbulb.implements(lightbulb.SlashCommand)
async def ban(ctx):
    member = ctx.options.member
    guild = ctx.get_guild()

    if not guild or not member:
        await ctx.respond("❌ Invalid member or guild.")
        return

    try:
        await ctx.bot.rest.ban_user(guild, member)
        await ctx.respond(f"✅ {member} has been banned.")
        logger.info(f"{ctx.author} banned {member}")
    except Exception as e:
        await ctx.respond(f"❌ Failed to ban {member}.")
        logger.warning(f"Failed to ban {member}: {e}")

# Unban Command
@plugin.command()
@lightbulb.option("user", "The user ID to unban.", type=str)
@lightbulb.command("unban", "Unbans a previously banned user.")
@lightbulb.implements(lightbulb.SlashCommand)
async def unban(ctx):
    user_id = ctx.options.user
    guild = ctx.get_guild()

    if not guild:
        await ctx.respond("❌ Invalid guild.")
        return

    try:
        await ctx.bot.rest.unban_user(guild, user_id)
        await ctx.respond(f"✅ User <@{user_id}> has been unbanned.")
        logger.info(f"{ctx.author} unbanned {user_id}")
    except Exception as e:
        await ctx.respond(f"❌ Failed to unban user <@{user_id}>.")
        logger.warning(f"Failed to unban {user_id}: {e}")

# Purge Command
@plugin.command()
@lightbulb.option("amount", "Number of messages to delete.", type=int)
@lightbulb.command("purge", "Deletes a set number of messages in a channel.")
@lightbulb.implements(lightbulb.SlashCommand)
async def purge(ctx):
    amount = ctx.options.amount
    channel = ctx.get_channel()

    if amount <= 0:
        await ctx.respond("❌ Please specify a valid number of messages to delete.")
        return

    try:
        messages = await ctx.bot.rest.fetch_messages(channel).limit(amount)
        await ctx.bot.rest.delete_messages(channel, messages)
        await ctx.respond(f"✅ Deleted {amount} messages.")
        logger.info(f"{ctx.author} purged {amount} messages in {channel}")
    except Exception as e:
        await ctx.respond("❌ Failed to delete messages.")
        logger.warning(f"Failed to purge messages: {e}")

# Timeout/Mute Command
@plugin.command()
@lightbulb.option("member", "The user to timeout.", type=hikari.Member)
@lightbulb.option("duration", "Timeout duration in seconds.", type=int)
@lightbulb.command("mute", "Mute a user by putting them in timeout for a specified duration.")
@lightbulb.implements(lightbulb.SlashCommand)
async def timeout(ctx: lightbulb.Context) -> None:
    member = ctx.options.member
    duration = ctx.options.duration
    guild = ctx.get_guild()

    if duration <= 0:
        await ctx.respond("❌ Please specify a duration greater than 0 seconds.")
        return

    timeout_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration)

    try:
        await ctx.bot.rest.edit_member(
            guild,
            member,
            communication_disabled_until=timeout_until
        )
        await ctx.respond(f"✅ {member} has been timed out for {duration} seconds.")
        logger.info(f"{ctx.author} timed out {member} for {duration} seconds.")
    except Exception as e:
        await ctx.respond("❌ Failed to timeout the member.")
        logger.warning(f"Failed to timeout {member}: {e}")

# Load the plugin into the bot
def load(bot):
    bot.add_plugin(plugin)
    logger.info("Moderation extension loaded.")

def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Moderation extension unloaded.")
