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

# Заменить Telegram ID (@userinfobot)
ADMIN_USER_IDS = {}

# Список сотрудников: {user_id: "Имя"}
KNOWN_EMPLOYEES = {
    467500951: "Хорошенин Сергей ",

    # Добавить остальных
}


# === 2. Проверка переменных окружения ===
missing_vars = []
for var in ["BOT_TOKEN", "SHEET_ID", "GOOGLE_CREDENTIALS"]:
    if not os.getenv(var):
        missing_vars.append(var)
if missing_vars:
    print(f"❌ Не заданы переменные: {', '.join(missing_vars)}")
    sys.exit(1)


# === 3. Инициализация Google Sheets ===
try:
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SHEET_ID)
    try:
        log = sh.worksheet("TimeLog")
    except WorksheetNotFound:
        log = sh.add_worksheet(title="TimeLog", rows="1000", cols="5")
        log.append_row(["Дата/время", "User ID", "Имя", "Действие", "Карта"])
    print("✅ Google Sheets готовы")
except Exception as e:
    print(f"❌ Ошибка Sheets: {e}")
    traceback.print_exc()
    sys.exit(1)


# === 4. Инициализация бота ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
user_actions = {}

# Общее меню для сотрудников
USER_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
        [KeyboardButton(text="Отправить геолокацию", request_location=True)]
    ],
    resize_keyboard=True
)


# === 5. Хэндлеры ===

@dp.message(F.text == "/start")
async def start(message: Message):
    user_id = message.from_user.id
    if user_id in ADMIN_USER_IDS:
        admin_menu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📊 Отчёт: кто пришёл/ушёл")],
                [KeyboardButton(text="⚠️ Кто не отметился")]
            ],
            resize_keyboard=True
        )
        await message.answer("Панель руководителя:", reply_markup=admin_menu)
    else:
        await message.answer(
            "Привет! Бот учёта рабочего времени.\n"
            "Выбери действие и отправь геолокацию 👇",
            reply_markup=USER_MENU
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

    # Яндекс.Карты с маркером
    yandex_link = f"https://yandex.ru/maps/?pt={lon},{lat}&z=18"

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    now = datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Сохраняем только: время, ID, имя, действие, ссылку
        log.append_row([now, uid, message.from_user.full_name, action, yandex_link])
        print(f"✅ {action} — {message.from_user.full_name} — {now}")
    except Exception as e:
        print(f"❌ Ошибка записи: {e}")
        await message.answer("⚠️ Не удалось сохранить запись.")
        return

    await message.answer(
        f"{action}, зафиксирован ✅\n{now}\n<a href='{yandex_link}'>📍 Открыть в Яндекс.Картах</a>",
        reply_markup=USER_MENU
    )


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

        came = []
        left = []
        for r in today_records:
            name = r.get("Имя", "—")
            action = r.get("Действие", "")
            time_str = r.get("Дата/время", "")[-8:]  # HH:MM:SS
            line = f"• {name} — {time_str}"
            if action == "Пришёл":
                came.append(line)
            elif action == "Ушёл":
                left.append(line)

        lines = ["<b>📅 Отчёт за сегодня:</b>"]

        if came:
            lines.append("\n<b>🟢 Пришли:</b>")
            lines.extend(came)
        else:
            lines.append("\n<b>🟢 Пришли:</b>\n— Никто")

        if left:
            lines.append("\n<b>🔴 Ушли:</b>")
            lines.extend(left)
        else:
            lines.append("\n<b>🔴 Ушли:</b>\n— Никто")

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

        missing = [
            f"• {name}" for uid, name in KNOWN_EMPLOYEES.items()
            if str(uid) not in today_uids
        ]

        if not missing:
            await message.answer("🎉 Все сотрудники отметились сегодня!")
        else:
            response = "<b>❌ Не отметились сегодня:</b>\n" + "\n".join(missing)
            await message.answer(response, parse_mode="HTML")

    except Exception as e:
        print(f"❌ Ошибка 'не отметились': {e}")
        await message.answer("⚠️ Ошибка при проверке неотметившихся.")


# === 6. Запуск ===
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
        print(f"🔴 Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
