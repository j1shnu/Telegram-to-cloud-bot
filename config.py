import os
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "downloads")
if not os.path.isabs(UPLOAD_DIR):
    UPLOAD_DIR = os.path.join(BASE_DIR, UPLOAD_DIR)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not all([API_ID, API_HASH, BOT_TOKEN]):
    print("Error: API_ID, API_HASH, and BOT_TOKEN must be set in .env")
