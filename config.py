import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEFAULT_REACTION = os.environ.get("DEFAULT_REACTION", "\U0001f44d")
MAX_REACTIONS = 3

WEBHOOK = os.environ.get("WEBHOOK", "false").lower() == "true"
PORT = int(os.environ.get("PORT", 8080))
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "MyNameIsAtheer")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "")
BIG_REACTION = os.environ.get("BIG_REACTION", "false").lower() == "true"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
