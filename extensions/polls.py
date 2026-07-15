import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

_rest: hikari.api.RESTClient | None = None

POLL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest


@loader.command
class Poll(lightbulb.SlashCommand, name="poll", description="Create a poll."):
    question = lightbulb.string("question", "The poll question.")
    options = lightbulb.string("options", "Options separated by commas (2-10 options).")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        opts = [o.strip() for o in self.options.split(",") if o.strip()]
        if len(opts) < 2:
            await ctx.respond("❌ Please provide at least 2 options separated by commas.")
            return
        if len(opts) > 10:
            await ctx.respond("❌ Maximum 10 options allowed.")
            return

        lines = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(opts))
        embed = hikari.Embed(
            title=f"📊 {self.question}",
            description=lines,
            color=0x5865F2,
        )
        embed.set_footer(text=f"Poll by {ctx.user.username}")

        await ctx.respond(embed=embed)
        msg = await ctx.fetch_last_response()

        if _rest is None:
            return
        for i in range(len(opts)):
            try:
                await _rest.add_reaction(ctx.channel_id, msg.id, POLL_EMOJIS[i])
            except Exception as e:
                logger.warning(f"Failed to add reaction: {e}")
                break
