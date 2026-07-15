import random
import lightbulb
import hikari
import logging
from config import config

logger = logging.getLogger(__name__)

loader = lightbulb.Loader(should_load_hook=lambda: getattr(config, "ENABLE_FUN_COMMANDS", True))


@loader.command
class EightBall(lightbulb.SlashCommand, name="8ball", description="Ask the Magic 8-Ball a question."):
    question = lightbulb.string("question", "Your question.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.",
            "Yes, definitely.", "You may rely on it.", "As I see it, yes.",
            "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful.",
        ]
        embed = hikari.Embed(color=0x1a0066)
        embed.add_field("Question", self.question, inline=False)
        embed.add_field("Answer", random.choice(responses), inline=False)
        await ctx.respond(embed=embed)


@loader.command
class CoinFlip(lightbulb.SlashCommand, name="coinflip", description="Flip a coin."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        result = random.choice(["Heads", "Tails"])
        await ctx.respond(f"🪙 **{result}!**")


@loader.command
class Roll(lightbulb.SlashCommand, name="roll", description="Roll a dice."):
    sides = lightbulb.integer("sides", "Number of sides (default 6).", default=6, min_value=2, max_value=1000)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        result = random.randint(1, self.sides)
        await ctx.respond(f"🎲 You rolled a **{result}** (d{self.sides})")


@loader.command
class Choose(lightbulb.SlashCommand, name="choose", description="Choose between options."):
    options = lightbulb.string("options", "Options separated by commas.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        choices = [o.strip() for o in self.options.split(",") if o.strip()]
        if len(choices) < 2:
            await ctx.respond("❌ Please provide at least 2 options separated by commas.")
            return
        chosen = random.choice(choices)
        await ctx.respond(f"🤔 I choose: **{chosen}**")


@loader.command
class HighFive(lightbulb.SlashCommand, name="highfive", description="Give someone a high five!"):
    user = lightbulb.user("user", "User to high five.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.respond(f"🙌 {ctx.user.mention} gave {self.user.mention} a high five!")
