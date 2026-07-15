import os
import hikari
import lightbulb
import logging
import time
from config import config  # Use centralized config

# Set up logging
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,  # Dynamically adjust logging level
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_logs.log", mode='a'),
    ]
)

BOT_START_TIME = time.time()
logger = logging.getLogger(__name__)

# Bot initialization
bot = lightbulb.BotApp(
    token=config.TOKEN,
    prefix=config.PREFIX,
    intents=hikari.Intents.ALL_UNPRIVILEGED,
)

logger.info("Starting AtlasBot...")

# Load extensions dynamically with error handling
def load_extensions():
    for file in os.listdir("extensions"):
        if file.endswith(".py"):
            ext_name = f"extensions.{file[:-3]}"
            try:
                bot.load_extensions(ext_name)
                logger.info(f"Loaded extension: {ext_name}")
            except Exception as e:
                logger.exception(f"Failed to load extension {ext_name}")

load_extensions()

@bot.listen(hikari.StartedEvent)
async def on_starting(event: hikari.StartedEvent) -> None:
    await bot.rest.fetch_application()  # Ensures bot fetches latest command state
    await bot.sync_application_commands()
    print("✅ Synced application commands.")

# Run the bot
if __name__ == "__main__":
    bot.run()