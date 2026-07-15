import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Polls")

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]


@plugin.command()
@lightbulb.option("option4", "Fourth option (optional).", type=str, default=None)
@lightbulb.option("option3", "Third option (optional).", type=str, default=None)
@lightbulb.option("option2", "Second option.", type=str)
@lightbulb.option("option1", "First option.", type=str)
@lightbulb.option("question", "The poll question.", type=str)
@lightbulb.command("poll", "Create a poll with up to 4 options.")
@lightbulb.implements(lightbulb.SlashCommand)
async def poll(ctx: lightbulb.Context) -> None:
    options = [o for o in [
        ctx.options.option1,
        ctx.options.option2,
        ctx.options.option3,
        ctx.options.option4,
    ] if o is not None]

    lines = [f"**{ctx.options.question}**\n"]
    for emoji, option in zip(NUMBER_EMOJIS, options):
        lines.append(f"{emoji}  {option}")

    embed = hikari.Embed(description="\n".join(lines), color=0x5865F2)
    embed.set_footer(text=f"Poll by {ctx.author.username}")

    response = await ctx.respond(embed=embed)
    message = await response.message()

    for emoji in NUMBER_EMOJIS[:len(options)]:
        await plugin.bot.rest.add_reaction(ctx.channel_id, message.id, emoji)

    logger.info(f"Poll created by {ctx.author} in guild {ctx.guild_id}: {ctx.options.question!r}")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Polls extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Polls extension unloaded.")
