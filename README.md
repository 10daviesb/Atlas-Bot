# 🌌 AtlasBot

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Feature Progress](https://img.shields.io/badge/progress-5%25-red)
![Code Quality](https://img.shields.io/badge/code%20quality-excellent-brightgreen)

AtlasBot is a feature-rich Discord bot built using the [Hikari](https://github.com/hikari-py/hikari) and [Lightbulb](https://github.com/tandemdude/hikari-lightbulb) frameworks. It provides moderation, utility, and administrative commands to enhance your Discord server experience.

---

## 🌍 Vision for AtlasBot

AtlasBot is not just another Discord bot—it's a **long-term project** with a bold goal: to be the **one-stop shop** for all Discord server needs. Many servers rely on 5-10 different bots, each with overlapping features and inconsistent functionality. AtlasBot aims to solve this problem by being the **only bot you'll ever need**.

### Why "Atlas"?
The name "Atlas" reflects the bot's mission to carry the weight of all server needs on its shoulders, just like the mythological figure Atlas. Whether it's moderation, entertainment, utility, or advanced server management, AtlasBot will handle it all.

### What Makes AtlasBot Different?
- **Comprehensive Features**: From moderation to music, games, and beyond, AtlasBot will cover every aspect of server management and engagement.
- **Customizability**: Server admins will have full control over which features to enable or disable, ensuring the bot adapts to their specific needs.
- **Community-Driven Development**: Suggestions and feedback are welcome! AtlasBot will evolve based on the needs of its users.
- **Reliability**: Built with robust frameworks and best practices, AtlasBot will be a dependable tool for any server.

---

## 🚀 Features

- **Moderation Commands**: Kick, ban, unban, purge messages, and timeout users.
- **Utility Commands**: Check bot latency, uptime, and sync commands.
- **Admin Commands**: Reload extensions dynamically.
- **Customizable**: Easily configurable via `.env` file.

---

## 🛠️ Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/10daviesb/AtlasBot.git
   cd AtlasBot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory and add your bot token:
   ```env
   TOKEN="your-bot-token"
   PREFIX="!"
   DEBUG=True
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

---

## 📜 Commands

### Moderation
- `/kick <member>`: Kicks a user from the server.
- `/ban <member>`: Bans a user from the server.
- `/unban <user_id>`: Unbans a previously banned user.
- `/purge <amount>`: Deletes a specified number of messages.
- `/mute <member> <duration>`: Mutes a user for a specified duration.

### Utility
- `/ping`: Check the bot's latency.
- `/uptime`: Displays how long the bot has been running.
- `/help`: Lists all available commands.
- `/sync`: Force sync all bot commands.

### Admin
- `/reload`: Reload all extensions dynamically.

---

## 🧰 Configuration

The bot uses a `.env` file for configuration. Below are the available options:

| Variable          | Description                          | Default |
|--------------------|--------------------------------------|---------|
| `TOKEN`           | Your bot's token                    | None    |
| `PREFIX`          | Command prefix for the bot           | `!`     |
| `DEBUG`           | Enable debug mode                   | `False` |

---

## 🤝 Contributing

Contributions are welcome! If you have ideas or suggestions to improve AtlasBot, feel free to fork the repository, submit a pull request, or open an issue. This project thrives on community feedback and collaboration.

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 💬 Support

If you encounter any issues or have questions, feel free to open an issue or contact the repository owner.

---

## 🌟 Acknowledgments

- [Hikari](https://github.com/hikari-py/hikari)
- [Lightbulb](https://github.com/tandemdude/hikari-lightbulb)
- [Python Dotenv](https://github.com/theskumar/python-dotenv)