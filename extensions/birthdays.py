import asyncio
import datetime
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {channel_id, role_id}
_bday_config: dict[int, dict] = {}
# (guild_id, user_id) -> (month, day)
_birthdays: dict[tuple[int, int], tuple[int, int]] = {}

_loop_task: asyncio.Task | None = None


def _today() -> tuple[int, int]:
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now.month, now.day)


async def _birthday_loop() -> None:
    last_checked: tuple[int, int] | None = None
    while True:
        await asyncio.sleep(60)
        today = _today()
        if today == last_checked:
            continue
        last_checked = today
        m, d = today
        for (guild_id, user_id), (bm, bd) in list(_birthdays.items()):
            if bm == m and bd == d:
                cfg = _bday_config.get(guild_id)
                if not cfg or _rest is None:
                    continue
                channel_id = cfg.get("channel_id")
                role_id = cfg.get("role_id")
                if channel_id:
                    try:
                        await _rest.create_message(channel_id, f"🎂 Happy birthday <@{user_id}>! 🎉")
                    except Exception as e:
                        logger.warning(f"Birthday message failed: {e}")
                if role_id:
                    try:
                        await _rest.add_role_to_member(guild_id, user_id, role_id, reason="Birthday role")
                    except Exception as e:
                        logger.warning(f"Birthday role failed: {e}")


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _loop_task
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthday_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER,
                role_id    INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                month    INTEGER NOT NULL,
                day      INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, role_id FROM birthday_config") as cur:
            for guild_id, channel_id, role_id in await cur.fetchall():
                _bday_config[guild_id] = {"channel_id": channel_id, "role_id": role_id}
        async with db.execute("SELECT guild_id, user_id, month, day FROM birthdays") as cur:
            for guild_id, user_id, month, day in await cur.fetchall():
                _birthdays[(guild_id, user_id)] = (month, day)
    _loop_task = asyncio.create_task(_birthday_loop())
    logger.info("Birthdays loaded.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    if _loop_task:
        _loop_task.cancel()


@loader.command
class BirthdaySetup(
    lightbulb.SlashCommand,
    name="birthdaysetup",
    description="Configure the birthday announcement channel and optional role.",
):
    channel = lightbulb.channel("channel", "Channel for birthday announcements.")
    role = lightbulb.role("role", "Role to give on birthdays.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        channel = self.channel
        role = self.role
        _bday_config[ctx.guild_id] = {"channel_id": channel.id, "role_id": role.id if role else None}
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO birthday_config (guild_id, channel_id, role_id) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, role_id = excluded.role_id
            """, (ctx.guild_id, channel.id, role.id if role else None))
            await db.commit()
        msg = f"✅ Birthday announcements will be sent to {channel.mention}."
        if role:
            msg += f" Birthday role: {role.mention}."
        await ctx.respond(msg)


# /birthday group
birthday_group = lightbulb.Group("birthday", "Manage your birthday.")


@birthday_group.register
class BirthdaySet(lightbulb.SlashCommand, name="set", description="Set your birthday."):
    month = lightbulb.integer("month", "Month (1-12).", min_value=1, max_value=12)
    day = lightbulb.integer("day", "Day (1-31).", min_value=1, max_value=31)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        try:
            datetime.date(2000, self.month, self.day)
        except ValueError:
            await ctx.respond("❌ Invalid date.")
            return
        key = (ctx.guild_id, ctx.user.id)
        _birthdays[key] = (self.month, self.day)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET month = excluded.month, day = excluded.day
            """, (ctx.guild_id, ctx.user.id, self.month, self.day))
            await db.commit()
        await ctx.respond(f"✅ Your birthday has been set to **{self.month}/{self.day}**.")


@birthday_group.register
class BirthdayClear(lightbulb.SlashCommand, name="clear", description="Remove your birthday."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        key = (ctx.guild_id, ctx.user.id)
        _birthdays.pop(key, None)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?", (ctx.guild_id, ctx.user.id))
            await db.commit()
        await ctx.respond("✅ Your birthday has been removed.")


@birthday_group.register
class BirthdayList(lightbulb.SlashCommand, name="list", description="List upcoming birthdays."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        entries = [(uid, m, d) for (gid, uid), (m, d) in _birthdays.items() if gid == ctx.guild_id]
        if not entries:
            await ctx.respond("ℹ️ No birthdays set for this server.")
            return
        today = _today()
        def sort_key(entry):
            _, m, d = entry
            if (m, d) < today:
                return (m + 12, d)
            return (m, d)
        entries.sort(key=sort_key)
        lines = [f"<@{uid}>: **{m}/{d}**" for uid, m, d in entries[:20]]
        await ctx.respond("🎂 **Upcoming Birthdays:**\n" + "\n".join(lines))


loader.command(birthday_group)
