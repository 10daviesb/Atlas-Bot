import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_bot_id: int | None = None

# guild_id -> {role_id, channel_id, message_id, button_label}
_verify_config: dict[int, dict] = {}

VERIFY_CUSTOM_ID = "atlas_verify_button"


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _bot_id
    _rest = event.app.rest
    me = await _rest.fetch_my_user()
    _bot_id = me.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS verification_config (
                guild_id     INTEGER PRIMARY KEY,
                role_id      INTEGER NOT NULL,
                channel_id   INTEGER,
                message_id   INTEGER,
                button_label TEXT NOT NULL DEFAULT 'Verify'
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, role_id, channel_id, message_id, button_label FROM verification_config") as cur:
            for guild_id, role_id, channel_id, message_id, button_label in await cur.fetchall():
                _verify_config[guild_id] = {
                    "role_id": role_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "button_label": button_label,
                }
    logger.info("Verification loaded.")


@loader.listener(hikari.InteractionCreateEvent)
async def on_interaction(event: hikari.InteractionCreateEvent) -> None:
    if not isinstance(event.interaction, hikari.ComponentInteraction):
        return
    if event.interaction.custom_id != VERIFY_CUSTOM_ID:
        return
    if _rest is None:
        return

    guild_id = event.interaction.guild_id
    if not guild_id:
        return

    cfg = _verify_config.get(guild_id)
    if not cfg:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            "❌ Verification is not configured.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return

    user_id = event.interaction.user.id
    role_id = cfg["role_id"]

    try:
        await _rest.add_role_to_member(guild_id, user_id, role_id, reason="Verification")
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            "✅ You have been verified!",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
    except hikari.ForbiddenError:
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            "❌ I don't have permission to give you the verified role.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
    except Exception as e:
        logger.warning(f"Verification failed for {user_id}: {e}")
        await event.interaction.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            "❌ Verification failed. Please contact a moderator.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )


@loader.command
class VerificationSetup(
    lightbulb.SlashCommand,
    name="verificationsetup",
    description="Configure the verification system.",
):
    role = lightbulb.role("role", "Role to give upon verification.")
    button_label = lightbulb.string("button_label", "Text on the verify button.", default="Verify")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return

        role = self.role
        _verify_config[ctx.guild_id] = {
            "role_id": role.id,
            "channel_id": None,
            "message_id": None,
            "button_label": self.button_label,
        }
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO verification_config (guild_id, role_id, button_label) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET role_id = excluded.role_id, button_label = excluded.button_label
            """, (ctx.guild_id, role.id, self.button_label))
            await db.commit()
        await ctx.respond(
            f"✅ Verification configured. Role: {role.mention}.\n"
            f"Use `/verificationpanel` to post the verification panel in a channel."
        )


@loader.command
class VerificationPanel(
    lightbulb.SlashCommand,
    name="verificationpanel",
    description="Post a verification panel with a button in this channel.",
):
    title = lightbulb.string("title", "Panel title.", default="Server Verification")
    description = lightbulb.string("description", "Panel description.", default="Click the button below to verify yourself and gain access to the server.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return

        cfg = _verify_config.get(ctx.guild_id)
        if not cfg:
            await ctx.respond("❌ Please run `/verificationsetup` first.")
            return

        embed = hikari.Embed(
            title=title,
            description=description,
            color=0x00CC99,
        )

        row = ctx.client.rest.build_message_action_row()
        row.add_interactive_button(
            hikari.ButtonStyle.SUCCESS,
            VERIFY_CUSTOM_ID,
            label=cfg["button_label"],
        )

        if _rest is None:
            await ctx.respond("❌ Not ready.")
            return

        msg = await _rest.create_message(ctx.channel_id, embed=embed, components=[row])
        _verify_config[ctx.guild_id]["channel_id"] = ctx.channel_id
        _verify_config[ctx.guild_id]["message_id"] = msg.id

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                UPDATE verification_config SET channel_id = ?, message_id = ? WHERE guild_id = ?
            """, (ctx.channel_id, msg.id, ctx.guild_id))
            await db.commit()

        await ctx.respond("✅ Verification panel posted!", flags=hikari.MessageFlag.EPHEMERAL)
