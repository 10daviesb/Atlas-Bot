import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Shop")

DB_PATH = "atlas.db"
CURRENCY = "🪙"


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                price       INTEGER NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                role_id     INTEGER,
                UNIQUE(guild_id, name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_inventory (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                item_id  INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, item_id)
            )
        """)
        await db.commit()
    logger.info("Shop DB initialized.")


async def _get_balance(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _deduct(guild_id: int, user_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute(
            "UPDATE economy SET balance = balance - ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id),
        )
        await db.commit()
    return True


@plugin.command()
@lightbulb.command("shop", "Browse and buy items from the server shop.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def shop(ctx: lightbulb.Context) -> None:
    pass


@shop.child
@lightbulb.command("list", "Browse the shop.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def shop_list(ctx: lightbulb.Context) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, name, price, description, role_id FROM shop_items WHERE guild_id = ? ORDER BY price",
            (ctx.guild_id,),
        ) as cur:
            items = await cur.fetchall()
    if not items:
        await ctx.respond("The shop is empty. Admins can add items with `/shop additem`.")
        return
    embed = hikari.Embed(title=f"{CURRENCY} Server Shop", color=0xF1C40F)
    for item_id, name, price, description, role_id in items:
        role_str = f" → gives <@&{role_id}>" if role_id else ""
        embed.add_field(
            f"{name} — {price:,} coins",
            description or "No description" + role_str,
            inline=False,
        )
    await ctx.respond(embed=embed)


@shop.child
@lightbulb.option("name", "Name of the item to buy.", type=str)
@lightbulb.command("buy", "Purchase an item from the shop.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def shop_buy(ctx: lightbulb.Context) -> None:
    name = ctx.options.name.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, price, role_id FROM shop_items WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (ctx.guild_id, name),
        ) as cur:
            item = await cur.fetchone()

    if not item:
        await ctx.respond(f"❌ No item named **{name}** in the shop.")
        return

    item_id, price, role_id = item
    ok = await _deduct(ctx.guild_id, ctx.author.id, price)
    if not ok:
        bal = await _get_balance(ctx.guild_id, ctx.author.id)
        await ctx.respond(f"❌ Not enough coins. You have **{bal:,}** but need **{price:,}**.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO shop_inventory (guild_id, user_id, item_id, quantity) VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + 1
        """, (ctx.guild_id, ctx.author.id, item_id))
        await db.commit()

    if role_id:
        try:
            await plugin.bot.rest.add_role_to_member(ctx.guild_id, ctx.author.id, role_id)
        except Exception as e:
            logger.warning(f"Could not assign shop role {role_id}: {e}")

    await ctx.respond(f"✅ Purchased **{name}** for {price:,} {CURRENCY}!")


@shop.child
@lightbulb.command("inventory", "See items you own.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def shop_inventory(ctx: lightbulb.Context) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT si.name, inv.quantity
            FROM shop_inventory inv
            JOIN shop_items si ON si.id = inv.item_id
            WHERE inv.guild_id = ? AND inv.user_id = ?
            ORDER BY si.name
        """, (ctx.guild_id, ctx.author.id)) as cur:
            rows = await cur.fetchall()
    if not rows:
        await ctx.respond("Your inventory is empty. Use `/shop buy` to get items!")
        return
    lines = [f"**{ctx.member.display_name}'s Inventory**"]
    for name, qty in rows:
        lines.append(f"• **{name}** × {qty}")
    await ctx.respond("\n".join(lines))


@shop.child
@lightbulb.option("role", "Role to give on purchase (optional).", type=hikari.Role, default=None)
@lightbulb.option("description", "Item description.", type=str, default="")
@lightbulb.option("price", "Price in coins.", type=int)
@lightbulb.option("name", "Item name.", type=str)
@lightbulb.command("additem", "Add an item to the shop.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def shop_additem(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    name = ctx.options.name.strip()
    price = ctx.options.price
    if price <= 0:
        await ctx.respond("❌ Price must be greater than 0.")
        return
    role: hikari.Role | None = ctx.options.role
    role_id = role.id if role else None
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO shop_items (guild_id, name, price, description, role_id) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild_id, name, price, ctx.options.description, role_id),
            )
            await db.commit()
        except Exception:
            await ctx.respond(f"❌ An item called **{name}** already exists.")
            return
    await ctx.respond(f"✅ Added **{name}** to the shop for {price:,} {CURRENCY}.")


@shop.child
@lightbulb.option("name", "Name of the item to remove.", type=str)
@lightbulb.command("removeitem", "Remove an item from the shop.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def shop_removeitem(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    name = ctx.options.name.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM shop_items WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (ctx.guild_id, name),
        ) as cur:
            item = await cur.fetchone()
        if not item:
            await ctx.respond(f"❌ No item named **{name}** found.")
            return
        await db.execute("DELETE FROM shop_items WHERE id = ?", (item[0],))
        await db.execute("DELETE FROM shop_inventory WHERE item_id = ?", (item[0],))
        await db.commit()
    await ctx.respond(f"✅ Removed **{name}** from the shop.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Shop extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Shop extension unloaded.")
