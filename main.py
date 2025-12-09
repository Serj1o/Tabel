# main.py
import os
import json
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ContentType
from aiogram.client.default import DefaultBotProperties

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
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Храним выбор действия (IN/OUT)
user_actions = {}

# Главное меню
menu = ReplyKeyboardMarkup(resize_keyboard=True)
menu.add("Пришёл на работу", "Ушёл с работы")
menu.add(KeyboardButton("Отправить геолокацию", request_location=True))


@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "Привет! Бот учёта рабочего времени.\n"
        "Выбери действие и отправь геолокацию 👇",
        reply_markup=menu
    )


@dp.message(F.text.in_(["Пришёл на работу", "Ушёл с работы"]))
async def choose_action(message: Message):
    uid = message.from_user.id

    if "Пришёл" in message.text:
        user_actions[uid] = "IN"
        text = "Отправь геолокацию для прихода"
    else:
        user_actions[uid] = "OUT"
        text = "Отправь геолокацию для ухода"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Отправить геолокацию", request_location=True))

    await message.answer(text, reply_markup=kb)


@dp.message(F.content_type == ContentType.LOCATION)
async def handle_location(message: Message):

    uid = message.from_user.id

    action = user_actions.get(uid, "IN")
    action_text = "Пришёл" if action == "IN" else "Ушёл"

    lat = message.location.latitude
    lon = message.location.longitude

    map_link = f"https://maps.google.com/?q={lat},{lon}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log.append_row([
        now, uid, message.from_user.full_name,
        action, lat, lon, map_link
    ])

    await message.answer(
        f"{action_text} зафиксирован ✅\n"
        f"{now}\n"
        f"{map_link}",
        reply_markup=menu
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
