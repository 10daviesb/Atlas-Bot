import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()

        self.TOKEN = os.getenv("TOKEN")
        self.PREFIX = os.getenv("PREFIX", "!")
        self.DEBUG = os.getenv("DEBUG", "False").lower() == "true"
        self.OWNER_ID = int(os.getenv("OWNER_ID", "0"))
        self.GUILD_ID = int(os.getenv("GUILD_ID", "0"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.ERROR_LOG_CHANNEL = int(os.getenv("ERROR_LOG_CHANNEL", "0"))

        self.DB_URI = os.getenv("DB_URI")
        self.REDIS_URL = os.getenv("REDIS_URL")

        self.ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0"))
        self.MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", "0"))

        self.ENABLE_WELCOME_MESSAGES = os.getenv("ENABLE_WELCOME_MESSAGES", "False").lower() == "true"
        self.ENABLE_LEVELING = os.getenv("ENABLE_LEVELING", "False").lower() == "true"
        self.ENABLE_FUN_COMMANDS = os.getenv("ENABLE_FUN_COMMANDS", "True").lower() == "true"
        self.ENABLE_MUSIC = os.getenv("ENABLE_MUSIC", "True").lower() == "true"

        self.LAVALINK_HOST = os.getenv("LAVALINK_HOST", "127.0.0.1")
        self.LAVALINK_PORT = int(os.getenv("LAVALINK_PORT", "2333"))
        self.LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")
        self.LAVALINK_SSL = os.getenv("LAVALINK_SSL", "False").lower() == "true"

config = Config()
