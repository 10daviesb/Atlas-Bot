import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Counting")

DB_PATH = "atlas.db"

# guild_id -> {channel_id, current, last_user_id}
_state: dict[int, dict] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS counting_config (
                guild_id     INTEGER PRIMARY KEY,
                channel_id   INTEGER NOT NULL,
                current      INTEGER NOT NULL DEFAULT 0,
                last_user_id INTEGER
            )
        """)
        await db.commit()
        async with db.execute(
            "SELECT guild_id, channel_id, current, last_user_id FROM counting_config"
        ) as cur:
            for guild_id, channel_id, current, last_user_id in await cur.fetchall():
                _state[guild_id] = {
                    "channel_id": channel_id,
                    "current": current,
                    "last_user_id": last_user_id,
                }
    logger.info(f"Counting loaded: {len(_state)} guilds.")


async def _reset(guild_id: int, channel_id: int, ruined_by: hikari.User | None = None) -> None:
    _state[guild_id]["current"] = 0
    _state[guild_id]["last_user_id"] = None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE counting_config SET current = 0, last_user_id = NULL WHERE guild_id = ?",
            (guild_id,),
        )
        await db.commit()
    if ruined_by:
        await plugin.bot.rest.create_message(
            channel_id,
            f"💥 {ruined_by.mention} ruined the count! Starting back from **1**.",
        )


@plugin.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot:
        return
    state = _state.get(event.guild_id)
    if not state or event.channel_id != state["channel_id"]:
        return

    content = (event.content or "").strip()
    try:
        number = int(content)
    except ValueError:
        try:
            await plugin.bot.rest.delete_message(event.channel_id, event.message_id)
        except Exception:
            pass
        return

    expected = state["current"] + 1
    is_same_user = state["last_user_id"] == event.author_id

    if number != expected or is_same_user:
        await plugin.bot.rest.add_reaction(event.channel_id, event.message_id, "❌")
        reason = "You can't count twice in a row!" if is_same_user else f"Wrong number! Expected **{expected}**."
        await _reset(event.guild_id, event.channel_id, event.author)
        await plugin.bot.rest.create_message(event.channel_id, f"❌ {reason}")
        return

    state["current"] = number
    state["last_user_id"] = event.author_id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE counting_config SET current = ?, last_user_id = ? WHERE guild_id = ?",
            (number, event.author_id, event.guild_id),
        )
        await db.commit()

    await plugin.bot.rest.add_reaction(event.channel_id, event.message_id, "✅")
    if number % 100 == 0:
        await plugin.bot.rest.create_message(
            event.channel_id,
            f"🎉 **{number}!** Amazing teamwork!",
        )


@plugin.command()
@lightbulb.option("channel", "Channel to use for counting.", type=hikari.TextableGuildChannel)
@lightbulb.command("countingsetup", "Set up the counting channel.")
@lightbulb.implements(lightbulb.SlashCommand)
async def countingsetup(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel: hikari.TextableGuildChannel = ctx.options.channel
    _state[ctx.guild_id] = {"channel_id": channel.id, "current": 0, "last_user_id": None}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO counting_config (guild_id, channel_id, current) VALUES (?, ?, 0)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, current = 0, last_user_id = NULL
        """, (ctx.guild_id, channel.id))
        await db.commit()
    await ctx.respond(f"✅ Counting channel set to {channel.mention}. Count starts at **1**!")


@plugin.command()
@lightbulb.command("countingdisable", "Disable the counting channel.")
@lightbulb.implements(lightbulb.SlashCommand)
async def countingdisable(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    _state.pop(ctx.guild_id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM counting_config WHERE guild_id = ?", (ctx.guild_id,))
        await db.commit()
    await ctx.respond("✅ Counting channel disabled.")


@plugin.command()
@lightbulb.command("countingcount", "See the current count.")
@lightbulb.implements(lightbulb.SlashCommand)
async def countingcount(ctx: lightbulb.Context) -> None:
    state = _state.get(ctx.guild_id)
    if not state:
        await ctx.respond("❌ No counting channel configured.")
        return
    await ctx.respond(f"📊 Current count: **{state['current']}** in <#{state['channel_id']}>.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Counting extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Counting extension unloaded.")
