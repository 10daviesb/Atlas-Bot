import ongaku
import ongaku.events as ongaku_events
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)

loader = lightbulb.Loader(should_load_hook=lambda: getattr(config, "ENABLE_MUSIC", True))

_client: ongaku.Client | None = None
_rest: hikari.api.RESTClient | None = None


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _client, _rest
    _rest = event.app.rest
    _client = ongaku.Client(event.app)
    logger.info("Music (ongaku) loaded.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    if _client:
        await _client.close()


@loader.listener(ongaku_events.TrackEndEvent)
async def on_track_end(event: ongaku_events.TrackEndEvent) -> None:
    # ongaku handles auto-play from queue automatically
    pass


async def _get_player(ctx: lightbulb.Context) -> ongaku.Player | None:
    """Get or create player, ensuring user is in a voice channel."""
    if not ctx.member:
        return None
    voice_state = ctx.client.cache.get_voice_state(ctx.guild_id, ctx.user.id) if ctx.client.cache else None
    if not voice_state or not voice_state.channel_id:
        await ctx.respond("❌ You need to be in a voice channel.")
        return None
    if _client is None:
        await ctx.respond("❌ Music is not ready yet.")
        return None
    try:
        player = _client.fetch_player(ctx.guild_id)
    except Exception:
        player = await _client.create_player(ctx.guild_id)
        await player.connect(voice_state.channel_id)
    return player


@loader.command
class Play(lightbulb.SlashCommand, name="play", description="Play a song or add it to the queue."):
    query = lightbulb.string("query", "Song name or URL.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        player = await _get_player(ctx)
        if player is None:
            return

        await ctx.defer()
        try:
            result = await _client.rest.load_track(self.query)
        except Exception as e:
            await ctx.respond(f"❌ Failed to load track: {e}")
            return

        if result is None or not result.tracks:
            await ctx.respond("❌ No results found.")
            return

        track = result.tracks[0]
        await player.queue.add(track)
        if not player.is_playing:
            await player.play()
        await ctx.respond(f"🎵 Added to queue: **{track.info.title}**")


@loader.command
class Stop(lightbulb.SlashCommand, name="stop", description="Stop music and leave the voice channel."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if _client is None:
            await ctx.respond("❌ Music is not ready.")
            return
        try:
            player = _client.fetch_player(ctx.guild_id)
            await player.stop()
            await player.disconnect()
        except Exception:
            pass
        await ctx.respond("⏹️ Stopped and disconnected.")


@loader.command
class Skip(lightbulb.SlashCommand, name="skip", description="Skip the current song."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if _client is None:
            await ctx.respond("❌ Music is not ready.")
            return
        try:
            player = _client.fetch_player(ctx.guild_id)
            await player.skip()
            await ctx.respond("⏭️ Skipped.")
        except Exception:
            await ctx.respond("❌ Nothing is playing.")


@loader.command
class Pause(lightbulb.SlashCommand, name="pause", description="Pause or resume the current song."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if _client is None:
            await ctx.respond("❌ Music is not ready.")
            return
        try:
            player = _client.fetch_player(ctx.guild_id)
            if player.is_paused:
                await player.set_pause(False)
                await ctx.respond("▶️ Resumed.")
            else:
                await player.set_pause(True)
                await ctx.respond("⏸️ Paused.")
        except Exception:
            await ctx.respond("❌ Nothing is playing.")


@loader.command
class Volume(lightbulb.SlashCommand, name="volume", description="Set the playback volume."):
    level = lightbulb.integer("level", "Volume (0-200).", min_value=0, max_value=200)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if _client is None:
            await ctx.respond("❌ Music is not ready.")
            return
        try:
            player = _client.fetch_player(ctx.guild_id)
            await player.set_volume(self.level)
            await ctx.respond(f"🔊 Volume set to **{self.level}%**.")
        except Exception:
            await ctx.respond("❌ Nothing is playing.")


@loader.command
class Queue(lightbulb.SlashCommand, name="queue", description="Show the current queue."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if _client is None:
            await ctx.respond("❌ Music is not ready.")
            return
        try:
            player = _client.fetch_player(ctx.guild_id)
            tracks = player.queue.tracks
        except Exception:
            await ctx.respond("❌ Nothing in the queue.")
            return

        if not tracks:
            await ctx.respond("ℹ️ The queue is empty.")
            return

        lines = [f"**{i+1}.** {t.info.title}" for i, t in enumerate(tracks[:15])]
        current = player.current
        now_playing = f"**Now Playing:** {current.info.title}\n\n" if current else ""
        await ctx.respond(f"{now_playing}**Queue:**\n" + "\n".join(lines))


@loader.command
class NowPlaying(lightbulb.SlashCommand, name="nowplaying", description="Show the currently playing song."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if _client is None:
            await ctx.respond("❌ Music is not ready.")
            return
        try:
            player = _client.fetch_player(ctx.guild_id)
            current = player.current
        except Exception:
            current = None

        if not current:
            await ctx.respond("❌ Nothing is playing.")
            return

        embed = hikari.Embed(title="Now Playing", color=0x1DB954)
        embed.add_field("Track", current.info.title, inline=False)
        embed.add_field("Author", current.info.author, inline=True)
        if current.info.uri:
            embed.add_field("URL", current.info.uri, inline=False)
        await ctx.respond(embed=embed)
