import asyncio
import datetime
import random
import re

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_bot_id: int | None = None

# giveaway_id -> {guild_id, channel_id, message_id, prize, end_time, winners, ended}
_giveaways: dict[int, dict] = {}
_giveaway_task: asyncio.Task | None = None

GIVEAWAY_EMOJI = "🎉"


def _parse_duration(text: str) -> int | None:
    """Parse duration string like '1h', '30m', '2d' into seconds."""
    m = re.fullmatch(r"(\d+)([smhd])", text.strip().lower())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2)
    return val * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


async def _end_giveaway(giveaway_id: int) -> None:
    data = _giveaways.get(giveaway_id)
    if not data or data.get("ended") or _rest is None:
        return
    data["ended"] = True

    channel_id = data["channel_id"]
    message_id = data["message_id"]
    prize = data["prize"]
    winner_count = data["winners"]

    try:
        reactions = await _rest.fetch_reactions_for_emoji(channel_id, message_id, GIVEAWAY_EMOJI)
        participants = [u for u in reactions if not u.is_bot and u.id != _bot_id]
    except Exception:
        participants = []

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))
        await db.commit()

    if not participants:
        try:
            await _rest.create_message(channel_id, f"🎉 Giveaway ended: **{prize}** — No valid participants.")
        except Exception:
            pass
        return

    winners = random.sample(participants, min(winner_count, len(participants)))
    mentions = ", ".join(w.mention for w in winners)
    try:
        await _rest.create_message(
            channel_id,
            f"🎉 Congratulations {mentions}! You won **{prize}**!"
        )
        msg = await _rest.fetch_message(channel_id, message_id)
        embed = hikari.Embed(
            title=f"🎁 {prize}",
            description=f"Winners: {mentions}",
            color=0xFF69B4,
        )
        await _rest.edit_message(channel_id, message_id, content="**GIVEAWAY ENDED**", embed=embed)
    except Exception as e:
        logger.warning(f"Giveaway end failed: {e}")


async def _giveaway_loop() -> None:
    while True:
        await asyncio.sleep(10)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        for gid, data in list(_giveaways.items()):
            if not data.get("ended") and data["end_time"] <= now:
                await _end_giveaway(gid)


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _bot_id, _giveaway_task
    _rest = event.app.rest
    me = await _rest.fetch_my_user()
    _bot_id = me.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                prize      TEXT NOT NULL,
                end_time   REAL NOT NULL,
                winners    INTEGER NOT NULL DEFAULT 1,
                ended      INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()
        async with db.execute(
            "SELECT id, guild_id, channel_id, message_id, prize, end_time, winners FROM giveaways WHERE ended = 0"
        ) as cur:
            for row in await cur.fetchall():
                gid, guild_id, channel_id, message_id, prize, end_time, winners = row
                _giveaways[gid] = {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "prize": prize,
                    "end_time": end_time,
                    "winners": winners,
                    "ended": False,
                }
    _giveaway_task = asyncio.create_task(_giveaway_loop())
    logger.info(f"Giveaways loaded: {len(_giveaways)} active.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    if _giveaway_task:
        _giveaway_task.cancel()


# /giveaway group
giveaway_group = lightbulb.Group("giveaway", "Manage giveaways.")


@giveaway_group.register
class GiveawayStart(lightbulb.SlashCommand, name="start", description="Start a giveaway."):
    prize = lightbulb.string("prize", "What are you giving away?")
    duration = lightbulb.string("duration", "Duration (e.g. 1h, 30m, 2d).")
    channel = lightbulb.channel("channel", "Channel for the giveaway.", default=None)
    winners = lightbulb.integer("winners", "Number of winners.", default=1, min_value=1, max_value=20)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        secs = _parse_duration(self.duration)
        if not secs:
            await ctx.respond("❌ Invalid duration. Examples: `30m`, `2h`, `1d`.")
            return

        ch = self.channel or ctx.get_channel()
        if ch is None:
            await ctx.respond("❌ Could not determine the channel.")
            return

        end_time = datetime.datetime.now(datetime.timezone.utc).timestamp() + secs
        end_dt = datetime.datetime.fromtimestamp(end_time, tz=datetime.timezone.utc)
        end_str = f"<t:{int(end_time)}:R>"

        embed = hikari.Embed(
            title=f"🎁 {self.prize}",
            description=f"React with {GIVEAWAY_EMOJI} to enter!\nEnds {end_str}\nWinners: **{self.winners}**",
            color=0xFF69B4,
        )
        msg = await _rest.create_message(ch.id, embed=embed)
        await _rest.add_reaction(ch.id, msg.id, GIVEAWAY_EMOJI)

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("""
                INSERT INTO giveaways (guild_id, channel_id, message_id, prize, end_time, winners, ended)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (ctx.guild_id, ch.id, msg.id, self.prize, end_time, self.winners))
            await db.commit()
            giveaway_id = cur.lastrowid

        _giveaways[giveaway_id] = {
            "guild_id": ctx.guild_id,
            "channel_id": ch.id,
            "message_id": msg.id,
            "prize": self.prize,
            "end_time": end_time,
            "winners": self.winners,
            "ended": False,
        }
        await ctx.respond(f"✅ Giveaway started in {ch.mention}!")


@giveaway_group.register
class GiveawayEnd(lightbulb.SlashCommand, name="end", description="End a giveaway early."):
    message_id = lightbulb.string("message_id", "Message ID of the giveaway.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        try:
            mid = int(self.message_id)
        except ValueError:
            await ctx.respond("❌ Invalid message ID.")
            return

        target = next((gid for gid, d in _giveaways.items() if d["message_id"] == mid and not d["ended"]), None)
        if target is None:
            await ctx.respond("❌ No active giveaway with that message ID.")
            return

        await _end_giveaway(target)
        await ctx.respond("✅ Giveaway ended.")


@giveaway_group.register
class GiveawayReroll(lightbulb.SlashCommand, name="reroll", description="Reroll a giveaway winner."):
    message_id = lightbulb.string("message_id", "Message ID of the ended giveaway.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        try:
            mid = int(self.message_id)
        except ValueError:
            await ctx.respond("❌ Invalid message ID.")
            return

        data = next((d for d in _giveaways.values() if d["message_id"] == mid), None)
        if data is None:
            await ctx.respond("❌ Giveaway not found.")
            return

        channel_id = data["channel_id"]
        try:
            reactions = await _rest.fetch_reactions_for_emoji(channel_id, mid, GIVEAWAY_EMOJI)
            participants = [u for u in reactions if not u.is_bot and u.id != _bot_id]
        except Exception:
            participants = []

        if not participants:
            await ctx.respond("❌ No participants found.")
            return

        winner = random.choice(participants)
        await _rest.create_message(channel_id, f"🎉 New winner: {winner.mention}! Congratulations!")
        await ctx.respond("✅ Rerolled.")


loader.command(giveaway_group)
