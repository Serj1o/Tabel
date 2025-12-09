# main.py
import os
import json
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")

# Google Sheets
if os.getenv("GOOGLE_CREDENTIALS"):
    gc = gspread.service_account_from_dict(json.loads(os.getenv("GOOGLE_CREDENTIALS")))
else:
    gc = gspread.service_account(filename="credentials.json")

sh = gc.open_by_key(SHEET_ID)
log = sh.worksheet("TimeLog")

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Клавиатура
menu = ReplyKeyboardMarkup(resize_keyboard=True)
menu.add("Пришёл на работу", "Ушёл с работы")
menu.add(KeyboardButton("Отправить геолокацию", request_location=True))

# Храним выбранное действие
user_actions = {}   # user_id → "IN" / "OUT"


@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "Привет! Бот учёта рабочего времени.\n"
        "Выбери действие и отправь геолокацию 👇",
        reply_markup=menu
    )


@dp.message_handler(lambda m: m.text in ["Пришёл на работу", "Ушёл с работы"])
async def choose_action(message: types.Message):

    user_id = message.from_user.id

    if "Пришёл" in message.text:
        user_actions[user_id] = "IN"
        text = "Отправь геолокацию для прихода"
    else:
        user_actions[user_id] = "OUT"
        text = "Отправь геолокацию для ухода"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Отправить геолокацию", request_location=True))

    await message.answer(text, reply_markup=kb)


@dp.message_handler(content_types=["location"])
async def handle_location(message: types.Message):

    user_id = message.from_user.id

    # Определяем действие
    action = user_actions.get(user_id, "IN")
    action_text = "Пришёл" if action == "IN" else "Ушёл"

    lat = message.location.latitude
    lon = message.location.longitude
    map_link = f"https://maps.google.com/?q={lat},{lon}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Пишем в таблицу
    log.append_row([
        now, user_id, message.from_user.full_name,
        action, lat, lon, map_link
    ])

    await message.answer(
        f"{action_text} зафиксирован ✅\n"
        f"{now}\n"
        f"{map_link}",
        reply_markup=menu
    )


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
