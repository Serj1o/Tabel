import os
import json
import gspread
from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ContentType
from aiogram.client.default import DefaultBotProperties
from datetime import datetime

sys.excepthook = handle_exception
# === Проверка переменных окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_RAW = os.getenv("GOOGLE_CREDENTIALS")

if not all([BOT_TOKEN, SHEET_ID, GOOGLE_CREDENTIALS_RAW]):
    missing = [v for v in ["BOT_TOKEN", "SHEET_ID", "GOOGLE_CREDENTIALS"] if not os.getenv(v)]
    raise EnvironmentError(f"Не заданы переменные окружения: {', '.join(missing)}")

# === Инициализация Google Sheets ===
try:
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SHEET_ID)
    log = sh.worksheet("TimeLog")
except Exception as e:
    raise SystemExit(f"Ошибка подключения к Google Sheets: {e}")

# === Инициализация бота ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_actions = {}

# === Клавиатуры (aiogram 3) ===
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
        [KeyboardButton(text="Отправить геолокацию", request_location=True)]
    ],
    resize_keyboard=True
)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("❌ Необработанная ошибка:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
