import random
import lightbulb
import hikari
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Fun")

EIGHT_BALL_RESPONSES = [
    "It is certain.", "It is decidedly so.", "Without a doubt.",
    "Yes, definitely.", "You may rely on it.", "As I see it, yes.",
    "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.",
    "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]


@plugin.command()
@lightbulb.option("question", "The question to ask the magic 8-ball.", type=str)
@lightbulb.command("8ball", "Ask the magic 8-ball a yes/no question.")
@lightbulb.implements(lightbulb.SlashCommand)
async def eight_ball(ctx: lightbulb.Context) -> None:
    response = random.choice(EIGHT_BALL_RESPONSES)
    await ctx.respond(f"🎱 **{ctx.options.question}**\n{response}")
    logger.info(f"8ball used by {ctx.author}")


@plugin.command()
@lightbulb.command("coinflip", "Flip a coin.")
@lightbulb.implements(lightbulb.SlashCommand)
async def coinflip(ctx: lightbulb.Context) -> None:
    result = random.choice(["Heads", "Tails"])
    await ctx.respond(f"🪙 {result}!")
    logger.info(f"coinflip used by {ctx.author}: {result}")


@plugin.command()
@lightbulb.option("sides", "Number of sides on the die (default: 6).", type=int, default=6)
@lightbulb.command("roll", "Roll a die.")
@lightbulb.implements(lightbulb.SlashCommand)
async def roll(ctx: lightbulb.Context) -> None:
    sides = ctx.options.sides
    if sides < 2:
        await ctx.respond("❌ A die must have at least 2 sides.")
        return
    result = random.randint(1, sides)
    await ctx.respond(f"🎲 You rolled a **{result}** (d{sides})")
    logger.info(f"roll d{sides} by {ctx.author}: {result}")


@plugin.command()
@lightbulb.option("choice2", "Second option.", type=str)
@lightbulb.option("choice1", "First option.", type=str)
@lightbulb.command("choose", "Let the bot choose between two options.")
@lightbulb.implements(lightbulb.SlashCommand)
async def choose(ctx: lightbulb.Context) -> None:
    pick = random.choice([ctx.options.choice1, ctx.options.choice2])
    await ctx.respond(f"🤔 I choose: **{pick}**")
    logger.info(f"choose used by {ctx.author}: picked {pick}")


@plugin.command()
@lightbulb.option("target", "The user to high-five.", type=hikari.Member)
@lightbulb.command("highfive", "High-five someone!")
@lightbulb.implements(lightbulb.SlashCommand)
async def highfive(ctx: lightbulb.Context) -> None:
    target = ctx.options.target
    await ctx.respond(f"🙌 {ctx.author.mention} high-fives {target.mention}!")
    logger.info(f"highfive from {ctx.author} to {target}")


def load(bot):
    if config.ENABLE_FUN_COMMANDS:
        bot.add_plugin(plugin)
        logger.info("Fun extension loaded.")
    else:
        logger.info("Fun extension skipped (ENABLE_FUN_COMMANDS=False).")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Fun extension unloaded.")
