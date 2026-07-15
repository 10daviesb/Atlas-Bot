import random
import ongaku
import ongaku.events as ongaku_events
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Music")

_client: ongaku.Client | None = None
_loop_modes: dict[int, bool] = {}  # guild_id -> loop enabled


def _get_client() -> ongaku.Client:
    if _client is None:
        raise RuntimeError("Lavalink client not initialised.")
    return _client


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _client
    _client = ongaku.Client(plugin.bot)
    _client.create_session(
        name="main",
        host=config.LAVALINK_HOST,
        port=config.LAVALINK_PORT,
        password=config.LAVALINK_PASSWORD,
        ssl=config.LAVALINK_SSL,
    )
    logger.info(f"Music: Lavalink session registered ({config.LAVALINK_HOST}:{config.LAVALINK_PORT})")


def _get_author_voice_channel(ctx: lightbulb.Context) -> hikari.Snowflake | None:
    voice_state = plugin.bot.cache.get_voice_state(ctx.guild_id, ctx.author.id)
    return voice_state.channel_id if voice_state else None


async def _get_or_create_player(ctx: lightbulb.Context) -> ongaku.Player | None:
    channel_id = _get_author_voice_channel(ctx)
    if not channel_id:
        await ctx.respond("❌ You must be in a voice channel first.")
        return None
    player = _get_client().create_player(ctx.guild_id)
    if not player.connected:
        await player.connect(channel_id)
    return player


@plugin.command()
@lightbulb.command("join", "Join your current voice channel.")
@lightbulb.implements(lightbulb.SlashCommand)
async def join(ctx: lightbulb.Context) -> None:
    channel_id = _get_author_voice_channel(ctx)
    if not channel_id:
        await ctx.respond("❌ You must be in a voice channel.")
        return
    player = _get_client().create_player(ctx.guild_id)
    await player.connect(channel_id)
    await ctx.respond(f"✅ Joined <#{channel_id}>.")
    logger.info(f"Joined voice {channel_id} in guild {ctx.guild_id}")


@plugin.command()
@lightbulb.option("query", "Song name or URL.", type=str)
@lightbulb.command("play", "Play a song or add it to the queue.")
@lightbulb.implements(lightbulb.SlashCommand)
async def play(ctx: lightbulb.Context) -> None:
    player = await _get_or_create_player(ctx)
    if player is None:
        return

    query = ctx.options.query
    search = query if query.startswith("http") else f"ytsearch:{query}"

    result = await _get_client().rest.load_track(search)

    if result is None:
        await ctx.respond("❌ No results found.")
        return

    if isinstance(result, ongaku.Playlist):
        for track in result.tracks:
            await player.add(track)
        await ctx.respond(f"✅ Queued **{len(result.tracks)}** tracks from **{result.info.name}**.")
        logger.info(f"{ctx.author} queued playlist '{result.info.name}' in guild {ctx.guild_id}")
    else:
        tracks = result if isinstance(result, list) else [result]
        track = tracks[0]
        await player.add(track)
        await ctx.respond(f"✅ Added **{track.info.title}** by {track.info.author} to the queue.")
        logger.info(f"{ctx.author} queued '{track.info.title}' in guild {ctx.guild_id}")

    if not player.track:
        await player.play()


@plugin.command()
@lightbulb.command("pause", "Pause or resume playback.")
@lightbulb.implements(lightbulb.SlashCommand)
async def pause(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player or not player.track:
        await ctx.respond("❌ Nothing is playing.")
        return
    await player.set_pause(not player.is_paused)
    await ctx.respond("⏸️ Paused." if player.is_paused else "▶️ Resumed.")


@plugin.command()
@lightbulb.command("skip", "Skip the current song.")
@lightbulb.implements(lightbulb.SlashCommand)
async def skip(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player or not player.track:
        await ctx.respond("❌ Nothing is playing.")
        return
    await player.skip()
    await ctx.respond("⏭️ Skipped.")
    logger.info(f"{ctx.author} skipped in guild {ctx.guild_id}")


@plugin.command()
@lightbulb.option("level", "Volume level (0–100).", type=int)
@lightbulb.command("volume", "Set the playback volume.")
@lightbulb.implements(lightbulb.SlashCommand)
async def volume(ctx: lightbulb.Context) -> None:
    level = ctx.options.level
    if not 0 <= level <= 100:
        await ctx.respond("❌ Volume must be between 0 and 100.")
        return
    player = _get_client().fetch_player(ctx.guild_id)
    if not player:
        await ctx.respond("❌ Not in a voice channel.")
        return
    await player.set_volume(level)
    await ctx.respond(f"🔊 Volume set to **{level}%**.")


@plugin.command()
@lightbulb.command("nowplaying", "Show the currently playing song.")
@lightbulb.implements(lightbulb.SlashCommand)
async def nowplaying(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player or not player.track:
        await ctx.respond("❌ Nothing is playing.")
        return
    track = player.track
    duration_s = track.info.length // 1000
    duration = f"{duration_s // 60}:{duration_s % 60:02d}"
    await ctx.respond(
        f"🎵 **Now Playing**\n"
        f"**{track.info.title}** by {track.info.author}\n"
        f"Duration: `{duration}` | {'🔁 Looping' if player.is_paused else '▶️ Playing'}"
    )


@plugin.command()
@lightbulb.command("queue", "Show the current song queue.")
@lightbulb.implements(lightbulb.SlashCommand)
async def queue(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player or (not player.track and not player.queue):
        await ctx.respond("📭 The queue is empty.")
        return
    lines = ["**Queue**"]
    if player.track:
        lines.append(f"▶️ **{player.track.info.title}** *(now playing)*")
    for i, track in enumerate(player.queue[:9], 1):
        lines.append(f"`{i}.` {track.info.title}")
    if len(player.queue) > 9:
        lines.append(f"*...and {len(player.queue) - 9} more*")
    await ctx.respond("\n".join(lines))


@plugin.listener(ongaku_events.TrackEndEvent)
async def on_track_end(event: ongaku_events.TrackEndEvent) -> None:
    if not _loop_modes.get(event.guild_id):
        return
    if getattr(event, "reason", None) in ("STOPPED", "REPLACED"):
        return
    player = _get_client().fetch_player(event.guild_id)
    if not player or not event.track:
        return
    await player.add(event.track)
    if not player.track:
        await player.play()


@plugin.command()
@lightbulb.command("loop", "Toggle loop mode for the current track.")
@lightbulb.implements(lightbulb.SlashCommand)
async def loop(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player or not player.track:
        await ctx.respond("❌ Nothing is playing.")
        return
    _loop_modes[ctx.guild_id] = not _loop_modes.get(ctx.guild_id, False)
    status = "enabled" if _loop_modes[ctx.guild_id] else "disabled"
    await ctx.respond(f"🔁 Loop **{status}**.")
    logger.info(f"Loop {status} in guild {ctx.guild_id}")


@plugin.command()
@lightbulb.command("shuffle", "Shuffle the queue.")
@lightbulb.implements(lightbulb.SlashCommand)
async def shuffle(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player or not player.queue:
        await ctx.respond("❌ Nothing in the queue to shuffle.")
        return
    random.shuffle(player.queue)
    await ctx.respond("🔀 Queue shuffled!")
    logger.info(f"{ctx.author} shuffled queue in guild {ctx.guild_id}")


@plugin.command()
@lightbulb.command("stop", "Stop playback and leave the voice channel.")
@lightbulb.implements(lightbulb.SlashCommand)
async def stop(ctx: lightbulb.Context) -> None:
    player = _get_client().fetch_player(ctx.guild_id)
    if not player:
        await ctx.respond("❌ Not in a voice channel.")
        return
    await player.disconnect()
    await ctx.respond("⏹️ Stopped and left the channel.")
    logger.info(f"{ctx.author} stopped music in guild {ctx.guild_id}")


def load(bot):
    if config.ENABLE_MUSIC:
        bot.add_plugin(plugin)
        logger.info("Music extension loaded.")
    else:
        logger.info("Music extension skipped (ENABLE_MUSIC=False).")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Music extension unloaded.")
