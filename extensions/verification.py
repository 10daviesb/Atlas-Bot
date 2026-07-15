import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Verification")

DB_PATH = "atlas.db"
VERIFY_BUTTON_ID = "atlas_verify"

# guild_id -> {unverified_role_id, verified_role_id}
_configs: dict[int, dict] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS verification_config (
                guild_id           INTEGER PRIMARY KEY,
                unverified_role_id INTEGER,
                verified_role_id   INTEGER NOT NULL
            )
        """)
        await db.commit()
        async with db.execute(
            "SELECT guild_id, unverified_role_id, verified_role_id FROM verification_config"
        ) as cur:
            for guild_id, unverified, verified in await cur.fetchall():
                _configs[guild_id] = {"unverified": unverified, "verified": verified}
    logger.info("Verification DB initialized.")


@plugin.listener(hikari.InteractionCreateEvent)
async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
    if not isinstance(event.interaction, hikari.ComponentInteraction):
        return
    if event.interaction.custom_id != VERIFY_BUTTON_ID:
        return

    guild_id = event.interaction.guild_id
    user_id = event.interaction.user.id
    cfg = _configs.get(guild_id)

    if not cfg:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="❌ Verification is not configured for this server.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return

    try:
        if cfg.get("unverified"):
            await plugin.bot.rest.remove_role_from_member(guild_id, user_id, cfg["unverified"])
        await plugin.bot.rest.add_role_to_member(guild_id, user_id, cfg["verified"])
    except Exception as e:
        logger.warning(f"Verification role update failed for {user_id} in {guild_id}: {e}")
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content="❌ Could not assign verified role. Please contact an admin.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return

    await event.interaction.create_initial_response(
        hikari.ResponseType.MESSAGE_CREATE,
        content="✅ You've been verified! Welcome to the server.",
        flags=hikari.MessageFlag.EPHEMERAL,
    )
    logger.info(f"User {user_id} verified in guild {guild_id}")


@plugin.command()
@lightbulb.option(
    "unverified_role",
    "Role to remove on verify (optional).",
    type=hikari.Role,
    default=None,
)
@lightbulb.option("verified_role", "Role to assign when verified.", type=hikari.Role)
@lightbulb.command("verificationsetup", "Configure the verification system.")
@lightbulb.implements(lightbulb.SlashCommand)
async def verificationsetup(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return

    verified: hikari.Role = ctx.options.verified_role
    unverified: hikari.Role | None = ctx.options.unverified_role
    unverified_id = unverified.id if unverified else None

    _configs[ctx.guild_id] = {"unverified": unverified_id, "verified": verified.id}

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO verification_config (guild_id, unverified_role_id, verified_role_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                unverified_role_id = excluded.unverified_role_id,
                verified_role_id   = excluded.verified_role_id
        """, (ctx.guild_id, unverified_id, verified.id))
        await db.commit()

    parts = [f"Verified role: {verified.mention}"]
    if unverified:
        parts.append(f"Unverified role (removed on verify): {unverified.mention}")
    await ctx.respond("✅ Verification configured.\n" + "\n".join(parts))


@plugin.command()
@lightbulb.option("message", "Text shown above the verify button.", type=str, default="Click the button below to verify and gain access to the server.")
@lightbulb.command("verificationpanel", "Post the verification button panel in this channel.")
@lightbulb.implements(lightbulb.SlashCommand)
async def verificationpanel(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    if ctx.guild_id not in _configs:
        await ctx.respond("❌ Run `/verificationsetup` first.")
        return

    embed = hikari.Embed(
        title="✅ Verification",
        description=ctx.options.message,
        color=0x57F287,
    )

    action_row = (
        plugin.bot.rest.build_action_row()
        .add_interactive_button(hikari.ButtonStyle.SUCCESS, VERIFY_BUTTON_ID, label="✅ Verify")
    )

    await plugin.bot.rest.create_message(ctx.channel_id, embed=embed, component=action_row)
    await ctx.respond("✅ Verification panel posted.", flags=hikari.MessageFlag.EPHEMERAL)


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Verification extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Verification extension unloaded.")
