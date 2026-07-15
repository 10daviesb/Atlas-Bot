import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None


async def _get_balance(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _set_balance(guild_id: int, user_id: int, amount: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (guild_id, user_id, balance) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance
        """, (guild_id, user_id, max(0, amount)))
        await db.commit()


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                guild_id INTEGER NOT NULL,
                item_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT    NOT NULL,
                price    INTEGER NOT NULL,
                role_id  INTEGER
            )
        """)
        await db.commit()
    logger.info("Shop loaded.")


# /shop group
shop_group = lightbulb.Group("shop", "Browse and manage the server shop.")


@shop_group.register
class ShopList(lightbulb.SlashCommand, name="list", description="Browse the server shop."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT item_id, name, price, role_id FROM shop_items WHERE guild_id = ? ORDER BY price",
                (ctx.guild_id,)
            ) as cur:
                items = await cur.fetchall()

        if not items:
            await ctx.respond("ℹ️ The shop is empty.")
            return

        lines = []
        for item_id, name, price, role_id in items:
            role_str = f" → {f'<@&{role_id}>' if role_id else ''}"
            lines.append(f"**#{item_id}** {name} — **{price} coins**{role_str}")

        bal = await _get_balance(ctx.guild_id, ctx.user.id)
        embed = hikari.Embed(title="🛍️ Server Shop", description="\n".join(lines), color=0x00CC99)
        embed.set_footer(text=f"Your balance: {bal} coins")
        await ctx.respond(embed=embed)


@shop_group.register
class ShopBuy(lightbulb.SlashCommand, name="buy", description="Buy an item from the shop."):
    item_id = lightbulb.integer("item_id", "Item ID to purchase.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT name, price, role_id FROM shop_items WHERE guild_id = ? AND item_id = ?",
                (ctx.guild_id, self.item_id)
            ) as cur:
                item = await cur.fetchone()

        if not item:
            await ctx.respond("❌ Item not found.")
            return

        name, price, role_id = item
        bal = await _get_balance(ctx.guild_id, ctx.user.id)
        if bal < price:
            await ctx.respond(f"❌ You need **{price} coins** but only have **{bal} coins**.")
            return

        await _set_balance(ctx.guild_id, ctx.user.id, bal - price)

        if role_id and _rest:
            try:
                await _rest.add_role_to_member(ctx.guild_id, ctx.user.id, role_id, reason=f"Shop purchase: {name}")
            except Exception as e:
                logger.warning(f"Failed to assign shop role: {e}")

        member_name = ctx.member.display_name if ctx.member else ctx.user.username
        await ctx.respond(f"✅ **{member_name}** purchased **{name}** for **{price} coins**!")


@shop_group.register
class ShopAdd(lightbulb.SlashCommand, name="add", description="Add an item to the shop. (Admin only)"):
    name = lightbulb.string("name", "Item name.")
    price = lightbulb.integer("price", "Price in coins.", min_value=1)
    role = lightbulb.role("role", "Role to give on purchase.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        role = self.role
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("""
                INSERT INTO shop_items (guild_id, name, price, role_id) VALUES (?, ?, ?, ?)
            """, (ctx.guild_id, self.name, self.price, role.id if role else None))
            await db.commit()
            item_id = cur.lastrowid
        role_str = f" (gives {role.mention})" if role else ""
        await ctx.respond(f"✅ Added **{self.name}** to the shop for **{self.price} coins**{role_str}. ID: `{item_id}`")


@shop_group.register
class ShopRemove(lightbulb.SlashCommand, name="remove", description="Remove an item from the shop. (Admin only)"):
    item_id = lightbulb.integer("item_id", "Item ID to remove.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM shop_items WHERE guild_id = ? AND item_id = ?", (ctx.guild_id, self.item_id))
            await db.commit()
        await ctx.respond(f"✅ Item `{self.item_id}` removed from the shop.")


loader.command(shop_group)
