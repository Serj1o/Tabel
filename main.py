import os
import sys
import json
import traceback
from datetime import datetime
import zoneinfo 

import gspread
from gspread.exceptions import WorksheetNotFound

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ContentType
from aiogram.client.default import DefaultBotProperties


BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_RAW = os.getenv("GOOGLE_CREDENTIALS")

missing_vars = []
for var_name, var_value in [
    ("BOT_TOKEN", BOT_TOKEN),
    ("SHEET_ID", SHEET_ID),
    ("GOOGLE_CREDENTIALS", GOOGLE_CREDENTIALS_RAW),
]:
    if not var_value:
        missing_vars.append(var_name)

if missing_vars:
    print(f"❌ ОШИБКА: Не заданы переменные окружения: {', '.join(missing_vars)}")
    sys.exit(1)

print("✅ Переменные окружения загружены")


try:
    print("📂 Парсим учётные данные Google...")
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    client_email = creds.get("client_email", "неизвестно")
    print(f"📧 Авторизуемся как: {client_email}")

    gc = gspread.service_account_from_dict(creds)
    print(f"🔗 Открываем таблицу с ID: {SHEET_ID}")
    sh = gc.open_by_key(SHEET_ID)
    print(f"✅ Таблица '{sh.title}' успешно открыта")

    try:
        log = sh.worksheet("TimeLog")
        print("✅ Лист 'TimeLog' найден")
    except WorksheetNotFound:
        print("📝 Лист 'TimeLog' не найден. Создаём...")
        log = sh.add_worksheet(title="TimeLog", rows="1000", cols="7")
        log.append_row(["Дата/время", "User ID", "Имя", "Действие", "Широта", "Долгота", "Карта"])
        print("✅ Лист 'TimeLog' создан с заголовками")

except json.JSONDecodeError as e:
    print(f"❌ Ошибка: GOOGLE_CREDENTIALS — невалидный JSON: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Ошибка подключения к Google Sheets: {e}")
    traceback.print_exc()
    sys.exit(1)


try:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    user_actions = {}  

    menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
            [KeyboardButton(text="Отправить геолокацию", request_location=True)]
        ],
        resize_keyboard=True
    )

except Exception as e:
    print(f"❌ Ошибка инициализации бота: {e}")
    traceback.print_exc()
    sys.exit(1)



@dp.message(F.text == "/start")
async def start(message: Message):
    print(f"📨 Получен /start от {message.from_user.full_name} (ID: {message.from_user.id})")
    await message.answer(
        "Привет! Бот учёта рабочего времени.\n"
        "Выбери действие и отправь геолокацию 👇",
        reply_markup=menu
    )


@dp.message(F.text.in_(["Пришёл на работу", "Ушёл с работы"]))
async def choose_action(message: Message):
    uid = message.from_user.id
    if "Пришёл" in message.text:
        user_actions[uid] = "Пришёл"
        text = "Отправь геолокацию для прихода"
    else:
        user_actions[uid] = "Ушёл"
        text = "Отправь геолокацию для ухода"

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить геолокацию", request_location=True)]],
        resize_keyboard=True
    )
    await message.answer(text, reply_markup=kb)


@dp.message(F.content_type == ContentType.LOCATION)
async def handle_location(message: Message):
    uid = message.from_user.id
    action = user_actions.get(uid, "Пришёл") 

    lat = message.location.latitude
    lon = message.location.longitude


    yandex_map_link = f"https://yandex.ru/maps/?pt={lon},{lat}&z=18"
    google_map_link = f"https://maps.google.com/?q={lat},{lon}"

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    now = datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")

    try:
        log.append_row([
            now, uid, message.from_user.full_name,
            action, #lat, lon, 
            yandex_map_link
            
        ])
        print(f"✅ Запись добавлена: {action} — {now} — {message.from_user.full_name}")
    except Exception as e:
        print(f"❌ Ошибка записи в Google Sheets: {e}")
        await message.answer("⚠️ Не удалось сохранить запись. Обратитесь к администратору.")
        return

    await message.answer(
        f"{action} зафиксирован ✅\n"
        f"{now}\n"
        f"<a href='{yandex_map_link}'>📍 Открыть на Яндекс.Картах</a>",
        reply_markup=menu
    )



async def main():
    print("🚀 Бот запущен и ожидает сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Бот остановлен вручную")
    except Exception as e:
        print(f"🔴 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)
