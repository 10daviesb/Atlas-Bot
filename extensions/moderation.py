import datetime
import lightbulb
import hikari
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()


@loader.command
class Kick(lightbulb.SlashCommand, name="kick", description="Kick a member from the server."):
    user = lightbulb.user("user", "User to kick.")
    reason = lightbulb.string("reason", "Reason for the kick.", default="No reason provided.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.KICK_MEMBERS):
            await ctx.respond("❌ You need the **Kick Members** permission.")
            return

        target_user = self.user
        # Fetch member to verify they are in the guild
        try:
            target_member = ctx.interaction.resolved.members.get(target_user.id)
            if target_member is None:
                target_member = await ctx.client.rest.fetch_member(ctx.guild_id, target_user.id)
        except hikari.NotFoundError:
            await ctx.respond("❌ That user is not in this server.")
            return

        if target_member.permissions & hikari.Permissions.ADMINISTRATOR:
            await ctx.respond("❌ You cannot kick an administrator.")
            return

        try:
            await ctx.client.rest.kick_user(ctx.guild_id, target_user.id, reason=self.reason)
            await ctx.respond(f"✅ Kicked **{target_user.username}**. Reason: {self.reason}")
        except hikari.ForbiddenError:
            await ctx.respond("❌ I don't have permission to kick that user.")


@loader.command
class Ban(lightbulb.SlashCommand, name="ban", description="Ban a user from the server."):
    user = lightbulb.user("user", "User to ban.")
    reason = lightbulb.string("reason", "Reason for the ban.", default="No reason provided.")
    delete_days = lightbulb.integer("delete_days", "Days of messages to delete (0-7).", default=0, min_value=0, max_value=7)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.BAN_MEMBERS):
            await ctx.respond("❌ You need the **Ban Members** permission.")
            return

        target_user = self.user
        try:
            await ctx.client.rest.ban_user(
                ctx.guild_id,
                target_user.id,
                delete_message_seconds=self.delete_days * 86400,
                reason=self.reason,
            )
            await ctx.respond(f"✅ Banned **{target_user.username}**. Reason: {self.reason}")
        except hikari.ForbiddenError:
            await ctx.respond("❌ I don't have permission to ban that user.")


@loader.command
class Unban(lightbulb.SlashCommand, name="unban", description="Unban a user."):
    user_id = lightbulb.string("user_id", "User ID to unban.")
    reason = lightbulb.string("reason", "Reason.", default="No reason provided.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.BAN_MEMBERS):
            await ctx.respond("❌ You need the **Ban Members** permission.")
            return
        try:
            uid = int(self.user_id)
        except ValueError:
            await ctx.respond("❌ Invalid user ID.")
            return
        try:
            await ctx.client.rest.unban_user(ctx.guild_id, uid, reason=self.reason)
            await ctx.respond(f"✅ Unbanned user <@{uid}>.")
        except hikari.NotFoundError:
            await ctx.respond("❌ That user is not banned.")
        except hikari.ForbiddenError:
            await ctx.respond("❌ I don't have permission to unban that user.")


@loader.command
class Purge(lightbulb.SlashCommand, name="purge", description="Delete recent messages."):
    amount = lightbulb.integer("amount", "Number of messages to delete (1-100).", min_value=1, max_value=100)
    user = lightbulb.user("user", "Only delete messages from this user.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_MESSAGES):
            await ctx.respond("❌ You need the **Manage Messages** permission.")
            return

        await ctx.respond("🗑️ Purging messages...", flags=hikari.MessageFlag.EPHEMERAL)

        messages = await ctx.client.rest.fetch_messages(ctx.channel_id).limit(self.amount + 1)
        target_user = self.user
        if target_user:
            messages = [m for m in messages if m.author.id == target_user.id]

        # Exclude messages older than 14 days
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        messages = [m for m in messages if m.created_at > cutoff]

        if not messages:
            await ctx.edit_last_response("ℹ️ No messages to delete.")
            return

        try:
            await ctx.client.rest.delete_messages(ctx.channel_id, messages)
            await ctx.edit_last_response(f"✅ Deleted **{len(messages)}** message(s).")
        except Exception as e:
            await ctx.edit_last_response(f"❌ Failed to delete messages: {e}")


@loader.command
class Mute(lightbulb.SlashCommand, name="mute", description="Timeout (mute) a member."):
    user = lightbulb.user("user", "User to mute.")
    duration = lightbulb.integer("duration", "Duration in minutes.", min_value=1, max_value=40320)
    reason = lightbulb.string("reason", "Reason.", default="No reason provided.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MODERATE_MEMBERS):
            await ctx.respond("❌ You need the **Timeout Members** permission.")
            return

        target_user = self.user
        until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=self.duration)

        try:
            await ctx.client.rest.edit_member(
                ctx.guild_id,
                target_user.id,
                communication_disabled_until=until,
                reason=self.reason,
            )
            await ctx.respond(f"✅ Muted **{target_user.username}** for **{self.duration}** minutes. Reason: {self.reason}")
        except hikari.ForbiddenError:
            await ctx.respond("❌ I don't have permission to timeout that user.")


@loader.command
class Unmute(lightbulb.SlashCommand, name="unmute", description="Remove a timeout from a member."):
    user = lightbulb.user("user", "User to unmute.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MODERATE_MEMBERS):
            await ctx.respond("❌ You need the **Timeout Members** permission.")
            return

        target_user = self.user
        try:
            await ctx.client.rest.edit_member(
                ctx.guild_id,
                target_user.id,
                communication_disabled_until=None,
                reason="Unmuted by moderator",
            )
            await ctx.respond(f"✅ Unmuted **{target_user.username}**.")
        except hikari.ForbiddenError:
            await ctx.respond("❌ I don't have permission to unmute that user.")
