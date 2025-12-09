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


# === 1. Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_RAW = os.getenv("GOOGLE_CREDENTIALS")

# ID руководителей (можно несколько)
ADMIN_USER_IDS = {467500951}  # ← замени на свой ID

# Список сотрудников: {user_id: "Имя"}
KNOWN_EMPLOYEES = {
    467500951: "Сергей (руководитель)",
    123456789: "Иван Петров",
    987654321: "Мария Сидорова",
    # Добавь сюда всех, кто должен отмечаться
}

# === 2. Проверка переменных окружения ===
missing_vars = []
for var_name, var_value in [
    ("BOT_TOKEN", BOT_TOKEN),
    ("SHEET_ID", SHEET_ID),
    ("GOOGLE_CREDENTIALS", GOOGLE_CREDENTIALS_RAW),
]:
    if not var_value:
        missing_vars.append(var_name)

if missing_vars:
    print(f"❌ ОШИБКА: Не заданы переменные: {', '.join(missing_vars)}")
    sys.exit(1)
print("✅ Переменные окружения загружены")


# === 3. Google Sheets ===
try:
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SHEET_ID)
    try:
        log = sh.worksheet("TimeLog")
    except WorksheetNotFound:
        log = sh.add_worksheet(title="TimeLog", rows="1000", cols="7")
        log.append_row(["Дата/время", "User ID", "Имя", "Действие", "Широта", "Долгота", "Карта"])
    print("✅ Google Sheets готовы")
except Exception as e:
    print(f"❌ Ошибка Sheets: {e}")
    traceback.print_exc()
    sys.exit(1)


# === 4. Telegram бот ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_actions = {}


# === 5. Меню и хэндлеры ===

@dp.message(F.text == "/start")
async def start(message: Message):
    user_id = message.from_user.id
    if user_id in ADMIN_USER_IDS:
        admin_menu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📊 Отчёт: кто пришёл/ушёл")],
                [KeyboardButton(text="⚠️ Кто не отметился")],
                [KeyboardButton(text="↩️ Назад к обычному меню")]
            ],
            resize_keyboard=True
        )
        await message.answer("Панель руководителя:", reply_markup=admin_menu)
    else:
        user_menu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
                [KeyboardButton(text="Отправить геолокацию", request_location=True)]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "Привет! Бот учёта рабочего времени.\n"
            "Выбери действие и отправь геолокацию 👇",
            reply_markup=user_menu
        )


@dp.message(F.text.in_(["Пришёл на работу", "Ушёл с работы"]))
async def choose_action(message: Message):
    uid = message.from_user.id
    user_actions[uid] = "Пришёл" if "Пришёл" in message.text else "Ушёл"
    text = "Отправь геолокацию для прихода" if user_actions[uid] == "Пришёл" else "Отправь геолокацию для ухода"

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

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    now = datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")

    try:
        log.append_row([now, uid, message.from_user.full_name, action, yandex_map_link])
        print(f"✅ {action} — {message.from_user.full_name} — {now}")
    except Exception as e:
        print(f"❌ Ошибка записи: {e}")
        await message.answer("⚠️ Не удалось сохранить запись.")
        return

    menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
            [KeyboardButton(text="Отправить геолокацию", request_location=True)]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"{action} зафиксирован ✅\n{now}\n<a href='{google_map_link}'>📍 В Google Maps</a>",
        reply_markup=menu
    )


@dp.message(F.text == "↩️ Назад к обычному меню")
async def back_to_user(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        return
    user_menu = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
            [KeyboardButton(text="Отправить геолокацию", request_location=True)]
        ],
        resize_keyboard=True
    )
    await message.answer("Режим сотрудника активирован.", reply_markup=user_menu)


@dp.message(F.text == "📊 Отчёт: кто пришёл/ушёл")
async def report_attendance(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Доступ запрещён.")
        return

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).strftime("%Y-%m-%d")

    try:
        records = log.get_all_records()
        today_records = [r for r in records if r.get("Дата/время", "").startswith(today)]

        if not today_records:
            await message.answer("📭 Сегодня никто не отметился.")
            return

        user_events = {}
        for r in today_records:
            uid = r.get("User ID")
            name = r.get("Имя", f"ID {uid}")
            action = r.get("Действие", "—")
            time_str = r.get("Дата/время", "")[-8:]
            if uid not in user_events:
                user_events[uid] = {"name": name, "actions": []}
            user_events[uid]["actions"].append(f"{action} в {time_str}")

        lines = ["<b>✅ Отмеченные сегодня:</b>"]
        for data in user_events.values():
            events = "; ".join(data["actions"])
            lines.append(f"• {data['name']}: {events}")

        await message.answer("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        print(f"❌ Ошибка отчёта: {e}")
        await message.answer("⚠️ Не удалось сформировать отчёт.")


@dp.message(F.text == "⚠️ Кто не отметился")
async def report_missing(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("❌ Доступ запрещён.")
        return

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).strftime("%Y-%m-%d")

    try:
        records = log.get_all_records()
        today_uids = {str(r.get("User ID")) for r in records if r.get("Дата/время", "").startswith(today)}

        missing = []
        for uid, name in KNOWN_EMPLOYEES.items():
            if str(uid) not in today_uids:
                missing.append(f"• {name} (ID: {uid})")

        if not missing:
            await message.answer("🎉 Все отметились!")
        else:
            lines = ["<b>❌ Не отметились сегодня:</b>"] + missing
            lines.append("\nℹ️ Используйте ID для поиска в таблице.")
            await message.answer("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        print(f"❌ Ошибка 'не отметились': {e}")
        await message.answer("⚠️ Ошибка при проверке неотметившихся.")


# === 6. Запуск ===
async def main():
    print("🚀 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Остановка...")
    except Exception as e:
        print(f"🔴 Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
