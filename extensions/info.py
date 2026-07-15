import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Info")


@plugin.command()
@lightbulb.option("member", "Member to look up (defaults to you).", type=hikari.Member, default=None)
@lightbulb.command("userinfo", "Show information about a user.")
@lightbulb.implements(lightbulb.SlashCommand)
async def userinfo(ctx: lightbulb.Context) -> None:
    target = ctx.options.member or ctx.member
    roles = [f"<@&{r}>" for r in target.role_ids if r != ctx.guild_id]

    embed = hikari.Embed(title=str(target.display_name), color=0x5865F2)
    embed.set_thumbnail(target.display_avatar_url or target.user.display_avatar_url)
    embed.add_field("Username", str(target.user), inline=True)
    embed.add_field("ID", str(target.id), inline=True)
    embed.add_field("Bot", "Yes" if target.user.is_bot else "No", inline=True)
    embed.add_field("Account Created", target.user.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field("Joined Server", target.joined_at.strftime("%d %b %Y") if target.joined_at else "Unknown", inline=True)
    embed.add_field(f"Roles ({len(roles)})", ", ".join(roles) if roles else "None", inline=False)

    await ctx.respond(embed=embed)
    logger.info(f"userinfo for {target} requested by {ctx.author}")


@plugin.command()
@lightbulb.command("serverinfo", "Show information about this server.")
@lightbulb.implements(lightbulb.SlashCommand)
async def serverinfo(ctx: lightbulb.Context) -> None:
    guild = ctx.get_guild()
    if not guild:
        await ctx.respond("❌ Could not fetch server info.")
        return

    channels = plugin.bot.cache.get_guild_channels_view_for_guild(guild.id)
    text_count = sum(1 for c in channels.values() if isinstance(c, hikari.TextableGuildChannel) and not isinstance(c, hikari.GuildVoiceChannel))
    voice_count = sum(1 for c in channels.values() if isinstance(c, hikari.GuildVoiceChannel))
    roles = guild.get_roles()

    embed = hikari.Embed(title=guild.name, color=0x5865F2)
    if guild.icon_url:
        embed.set_thumbnail(guild.icon_url)
    embed.add_field("Owner", f"<@{guild.owner_id}>", inline=True)
    embed.add_field("Created", guild.created_at.strftime("%d %b %Y"), inline=True)
    embed.add_field("Members", str(guild.member_count or "?"), inline=True)
    embed.add_field("Text Channels", str(text_count), inline=True)
    embed.add_field("Voice Channels", str(voice_count), inline=True)
    embed.add_field("Roles", str(len(roles)), inline=True)
    embed.set_footer(text=f"ID: {guild.id}")

    await ctx.respond(embed=embed)
    logger.info(f"serverinfo requested by {ctx.author} in guild {guild.id}")


@plugin.command()
@lightbulb.option("member", "Member whose avatar to show (defaults to you).", type=hikari.Member, default=None)
@lightbulb.command("avatar", "Show a user's avatar.")
@lightbulb.implements(lightbulb.SlashCommand)
async def avatar(ctx: lightbulb.Context) -> None:
    target = ctx.options.member or ctx.member
    url = target.display_avatar_url or target.user.display_avatar_url

    embed = hikari.Embed(title=f"{target.display_name}'s Avatar", color=0x5865F2)
    embed.set_image(url)
    await ctx.respond(embed=embed)


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Info extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Info extension unloaded.")
