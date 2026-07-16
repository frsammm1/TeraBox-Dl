import os

# Telegram API settings
API_ID = int(os.environ.get("API_ID", "123456")) # Will be replaced by env var on Heroku
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# TeraBox settings
NDUS_COOKIE = os.environ.get("NDUS_COOKIE", "Y2L5tvnteHuivzUYyyR0r65R6MZzrXpKgsvl5GJ1")
