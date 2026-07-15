# 🌌 AtlasBot

![Python Version](https://img.shields.io/badge/python-3.14%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Feature Progress](https://img.shields.io/badge/progress-85%25-yellowgreen)
![Code Quality](https://img.shields.io/badge/code%20quality-excellent-brightgreen)

AtlasBot is a feature-rich, fully customisable Discord bot built with [Hikari](https://github.com/hikari-py/hikari) and [Hikari-Lightbulb](https://github.com/tandemdude/hikari-lightbulb). It covers moderation, music, levelling, economy, games, community tools, and advanced admin controls — all in one bot.

---

## 🌍 Vision for AtlasBot

AtlasBot is not just another Discord bot — it's a **long-term project** with a bold goal: to be the **one-stop shop** for all Discord server needs. Many servers rely on 5–10 different bots, each with overlapping features and inconsistent behaviour. AtlasBot aims to solve this by being the **only bot you'll ever need**.

### Why "Atlas"?
The name "Atlas" reflects the bot's mission to carry the weight of all server needs on its shoulders, just like the mythological figure. Whether it's moderation, entertainment, utility, or advanced server management — AtlasBot handles it all.

### What Makes AtlasBot Different?
- 🔧 **Fully Customisable** — Admins can enable/disable any extension or individual command per server. Commands can even be restricted to specific roles.
- 🎵 **Music via Lavalink** — High-quality audio powered by Lavalink with queue, loop, shuffle, and volume control.
- 📈 **XP & Levelling** — Message-based XP system with leaderboards, rank cards, and level-up role rewards.
- 🪙 **Economy** — Coins, daily/work rewards, gambling, a server shop, and player-to-player transfers.
- 🎮 **Games** — Trivia, hangman, and a server-wide counting channel.
- 🛡️ **Moderation** — Full suite of mod tools with an audit log.
- 🤖 **Automation** — Autoroles, temp roles, verification gates, AFK detection, bump reminders, and more.

---

## 🚀 Features

### 🛡️ Moderation
- `/kick`, `/ban`, `/unban`, `/mute`, `/warn`, `/purge`
- Automod — spam detection, link blocking, word filter

### 🔧 Utility
- `/ping`, `/uptime`, `/avatar`, `/userinfo`, `/serverinfo`
- `/remind` — set timed reminders with natural duration syntax (`1h30m`, `2d`)

### 🎵 Music
- Lavalink-powered audio via [hikari-ongaku](https://github.com/itsmeow/hikari-ongaku)
- `/play`, `/pause`, `/skip`, `/stop`, `/queue`, `/nowplaying`, `/volume`, `/loop`, `/shuffle`

### 📈 Levelling
- XP per message (with image bonus), 60s cooldown
- `/rank`, `/leaderboard`
- `/levelrole add/remove/list` — auto-assign roles at configured levels

### 🪙 Economy
- `/balance`, `/daily`, `/work`, `/gamble`, `/pay`, `/richest`
- `/shop list/buy/inventory/additem/removeitem`

### 🎉 Community & Fun
- `/poll` — up to 4 options with auto reactions
- `/suggest` — suggestion board with admin approve/deny
- `/giveaway start/end/reroll`
- `/ticket open/close/add` — private support tickets
- `/8ball`, `/coinflip`, `/roll`, `/choose`, `/highfive`
- 🎂 Birthday announcements with optional birthday role
- ⭐ Starboard — pin popular messages automatically
- 📊 Counting channel — server-wide sequential counting game

### 🤖 Automation
- **Autoroles** — assign roles automatically on join (separate human/bot targets)
- **Temp Roles** — give a role for a fixed duration, auto-removed on expiry
- **Verification Gate** — button-click verification with role swap
- **AFK System** — `/afk` with auto-clear and mention notifications
- **Bump Reminder** — pings a role 2h after a Disboard bump
- **Stream Notifications** — Twitch live alerts in a configured channel
- **Reaction Roles** — assign roles via emoji reactions
- **Welcome Messages** — customisable join announcements
- **Audit Log** — logs joins, leaves, bans, edits, deletions, and role changes

### ⚙️ Admin & Config
- `/config extension enable/disable/list` — toggle entire extensions per server
- `/config command enable/disable/restrict/unrestrict` — fine-grained command control with role restrictions
- Custom commands — create server-specific slash commands with `/cc add/remove/list`

---

## 🛠️ Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/10daviesb/Atlas-Bot.git
   cd Atlas-Bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory:
   ```env
   TOKEN=your-bot-token
   PREFIX=!
   DEBUG=False
   OWNER_ID=your-discord-user-id
   ENABLE_LEVELING=True
   ENABLE_MUSIC=True
   ```

4. *(Optional)* Set up [Lavalink](https://github.com/lavalink-devs/Lavalink) for music support and point `LAVALINK_HOST`/`LAVALINK_PORT`/`LAVALINK_PASSWORD` at it in `.env`.

5. Run the bot:
   ```bash
   python bot.py
   ```

---

## 🧰 Configuration

All configuration is done via `.env`:

| Variable | Description | Default |
|---|---|---|
| `TOKEN` | Bot token | — |
| `PREFIX` | Legacy prefix | `!` |
| `DEBUG` | Debug logging | `False` |
| `OWNER_ID` | Bot owner's Discord ID | `0` |
| `GUILD_ID` | Dev guild for instant slash command sync | `0` |
| `ERROR_LOG_CHANNEL` | Channel ID for error tracebacks | `0` |
| `ENABLE_LEVELING` | Enable the XP/levelling system | `False` |
| `ENABLE_MUSIC` | Enable music commands | `True` |
| `ENABLE_WELCOME_MESSAGES` | Enable welcome messages | `False` |
| `LAVALINK_HOST` | Lavalink server host | `127.0.0.1` |
| `LAVALINK_PORT` | Lavalink server port | `2333` |
| `LAVALINK_PASSWORD` | Lavalink password | `youshallnotpass` |
| `TWITCH_CLIENT_ID` | Twitch API client ID (for stream notifications) | — |
| `TWITCH_CLIENT_SECRET` | Twitch API client secret | — |

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🌟 Acknowledgments

- [Hikari](https://github.com/hikari-py/hikari)
- [Hikari-Lightbulb](https://github.com/tandemdude/hikari-lightbulb)
- [hikari-ongaku](https://github.com/itsmeow/hikari-ongaku)
- [Lavalink](https://github.com/lavalink-devs/Lavalink)
- [aiosqlite](https://github.com/omnilib/aiosqlite)
