import hikari
import lightbulb
import logging
import time
from bot import BOT_START_TIME

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()


def _fmt_uptime(seconds: float) -> str:
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


@loader.command
class Ping(lightbulb.SlashCommand, name="ping", description="Check the bot's latency."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        start = time.perf_counter()
        await ctx.respond("🏓 Pinging...")
        elapsed = (time.perf_counter() - start) * 1000

        # Gateway heartbeat latency
        gateway_latency = ctx.client.app.heartbeat_latency * 1000 if hasattr(ctx.client.app, "heartbeat_latency") else 0

        embed = hikari.Embed(title="🏓 Pong!", color=0x00FF00)
        embed.add_field("Round-trip", f"{elapsed:.1f}ms", inline=True)
        if gateway_latency:
            embed.add_field("Gateway", f"{gateway_latency:.1f}ms", inline=True)
        await ctx.edit_last_response(content=None, embed=embed)


@loader.command
class Uptime(lightbulb.SlashCommand, name="uptime", description="Show how long the bot has been running."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        elapsed = time.time() - BOT_START_TIME
        await ctx.respond(f"⏱️ Bot has been running for **{_fmt_uptime(elapsed)}**.")


@loader.command
class Help(lightbulb.SlashCommand, name="help", description="Show a list of available commands."):
    command = lightbulb.string("command", "Command name to get help for.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if self.command:
            await ctx.respond(
                f"ℹ️ For detailed help on `/{self.command}`, try using it — slash command descriptions are built into Discord!"
            )
            return

        embed = hikari.Embed(
            title="Atlas Bot — Help",
            description=(
                "Use Discord's built-in slash command browser to explore all commands.\n"
                "Type `/` in chat to see available commands and their descriptions.\n\n"
                "**Categories:**\n"
                "• `/admin` — Bot administration\n"
                "• `/afk` — AFK status\n"
                "• `/automod` — AutoMod configuration\n"
                "• `/auditlog` — Audit log setup\n"
                "• `/autorole` — Auto-role management\n"
                "• `/balance`, `/daily`, `/work`, `/gamble`, `/pay`, `/richest` — Economy\n"
                "• `/birthday` — Birthday tracking\n"
                "• `/bumpsetup` — Bump reminders\n"
                "• `/cc` — Custom commands\n"
                "• `/config` — Per-server settings\n"
                "• `/counting*` — Counting channel\n"
                "• `/giveaway` — Giveaways\n"
                "• `/info`, `/userinfo`, `/serverinfo`, `/avatar` — Information\n"
                "• `/kick`, `/ban`, `/unban`, `/purge`, `/mute` — Moderation\n"
                "• `/play`, `/stop`, `/skip`, `/pause`, `/volume`, `/queue` — Music\n"
                "• `/ping`, `/uptime` — Utility\n"
                "• `/poll` — Polls\n"
                "• `/rank`, `/leaderboard`, `/levelrole` — Leveling\n"
                "• `/reactionrole` — Reaction roles\n"
                "• `/remind` — Reminders\n"
                "• `/shop` — Server shop\n"
                "• `/starboard` — Starboard\n"
                "• `/stream` — Stream notifications\n"
                "• `/suggest`, `/suggestion` — Suggestions\n"
                "• `/temprole` — Temporary roles\n"
                "• `/ticket`, `/ticketsetup` — Support tickets\n"
                "• `/8ball`, `/coinflip`, `/roll`, `/choose` — Fun\n"
                "• `/trivia`, `/hangman` — Games\n"
                "• `/verification*` — Verification\n"
            ),
            color=0x5865F2,
        )
        await ctx.respond(embed=embed)
