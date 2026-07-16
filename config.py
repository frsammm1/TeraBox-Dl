import os

# Telegram API settings (Set these in Heroku Environment Variables)
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# TeraBox settings
NDUS_COOKIE = os.environ.get("NDUS_COOKIE", "")
