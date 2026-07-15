import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()


@loader.command
class UserInfo(lightbulb.SlashCommand, name="userinfo", description="Show information about a user."):
    user = lightbulb.user("user", "User to look up.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        target_user = self.user or ctx.user
        member: hikari.Member | None = None
        if ctx.guild_id:
            try:
                member = await ctx.client.rest.fetch_member(ctx.guild_id, target_user.id)
            except hikari.NotFoundError:
                pass

        embed = hikari.Embed(title=f"User Info — {target_user.username}", color=0x5865F2)
        embed.set_thumbnail(target_user.avatar_url or target_user.default_avatar_url)
        embed.add_field("Username", str(target_user), inline=True)
        embed.add_field("ID", str(target_user.id), inline=True)
        embed.add_field("Bot", "Yes" if target_user.is_bot else "No", inline=True)

        created = target_user.created_at
        embed.add_field("Account Created", f"<t:{int(created.timestamp())}:F>", inline=False)

        if member:
            if member.joined_at:
                embed.add_field("Joined Server", f"<t:{int(member.joined_at.timestamp())}:F>", inline=False)
            if member.nickname:
                embed.add_field("Nickname", member.nickname, inline=True)
            roles = [f"<@&{r}>" for r in member.role_ids if r != ctx.guild_id]
            if roles:
                embed.add_field("Roles", ", ".join(roles[:10]), inline=False)

        await ctx.respond(embed=embed)


@loader.command
class ServerInfo(lightbulb.SlashCommand, name="serverinfo", description="Show information about this server."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.guild_id:
            await ctx.respond("❌ This command can only be used in a server.")
            return

        guild = await ctx.client.rest.fetch_guild(ctx.guild_id)
        owner = await ctx.client.rest.fetch_user(guild.owner_id)

        embed = hikari.Embed(title=guild.name, color=0x5865F2)
        if guild.icon_url:
            embed.set_thumbnail(guild.icon_url)
        embed.add_field("Owner", str(owner), inline=True)
        embed.add_field("ID", str(guild.id), inline=True)
        embed.add_field("Member Count", str(guild.member_count), inline=True)
        embed.add_field("Created", f"<t:{int(guild.created_at.timestamp())}:F>", inline=False)
        embed.add_field("Boost Level", str(guild.premium_tier), inline=True)
        embed.add_field("Boosts", str(guild.premium_subscription_count or 0), inline=True)

        await ctx.respond(embed=embed)


@loader.command
class Avatar(lightbulb.SlashCommand, name="avatar", description="Show a user's avatar."):
    user = lightbulb.user("user", "User whose avatar to show.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        target = self.user or ctx.user
        url = target.avatar_url or target.default_avatar_url
        embed = hikari.Embed(title=f"{target.username}'s Avatar", color=0x5865F2)
        embed.set_image(url)
        await ctx.respond(embed=embed)
