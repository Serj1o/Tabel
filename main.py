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
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


# === 1. Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_RAW = os.getenv("GOOGLE_CREDENTIALS")

# Заменить Telegram ID (@userinfobot)
ADMIN_USER_IDS = {653474435}

# Список сотрудников: {user_id: "Имя"}
KNOWN_EMPLOYEES = {
    467500951: "Хорошенин Сергей",
    653474435: "Рашидов Михаил"
    # Добавить остальных
}

SITES = ["Мичуринский", "Рязанский", "Зеленая Роща", "Калчуга"]


# === 2. Проверка переменных окружения ===
missing_vars = []
for var in ["BOT_TOKEN", "SHEET_ID", "GOOGLE_CREDENTIALS"]:
    if not os.getenv(var):
        missing_vars.append(var)
if missing_vars:
    print(f"Не заданы переменные: {', '.join(missing_vars)}")
    sys.exit(1)


# === 3. Инициализация Google Sheets ===
try:
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SHEET_ID)
    try:
        log = sh.worksheet("TimeLog")
        headers = log.row_values(1)
        if "Участок" not in headers:
            log.update_cell(1, len(headers) + 1, "Участок")
            print("Добавлен столбец 'Участок'")
    except WorksheetNotFound:
        log = sh.add_worksheet(title="TimeLog", rows="1000", cols="6")
        log.append_row(["Дата/время", "User ID", "Имя", "Действие", "Карта", "Участок"])
    print("Google Sheets готовы")
except Exception as e:
    print(f"Ошибка Sheets: {e}")
    traceback.print_exc()
    sys.exit(1)


# === 4. Инициализация бота и FSM ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# Состояния
class WorkStates(StatesGroup):
    choosing_site = State()
    choosing_action = State()
    awaiting_location = State()

# Кнопки
BACK_BUTTON = KeyboardButton(text="↩️ Назад")

SITE_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=site)] for site in SITES
    ] + [[BACK_BUTTON]],
    resize_keyboard=True
)

ACTION_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Пришёл на работу"), KeyboardButton(text="Ушёл с работы")],
        [BACK_BUTTON]
    ],
    resize_keyboard=True
)

LOCATION_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отправить геолокацию", request_location=True)],
        [BACK_BUTTON]
    ],
    resize_keyboard=True
)


# === 5. Хэндлеры ===

@dp.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in ADMIN_USER_IDS:
        admin_menu = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Отчёт: кто пришёл/ушёл")],
                [KeyboardButton(text="Кто не отметился")]
            ],
            resize_keyboard=True
        )
        await message.answer("Панель руководителя:", reply_markup=admin_menu)
    else:
        await state.set_state(WorkStates.choosing_site)
        await message.answer("Выберите участок:", reply_markup=SITE_KEYBOARD)


@dp.message(F.text == "↩️ Назад")
async def go_back(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == WorkStates.choosing_action.state:
        await state.set_state(WorkStates.choosing_site)
        await message.answer("Выберите участок:", reply_markup=SITE_KEYBOARD)
    elif current_state == WorkStates.awaiting_location.state:
        await state.set_state(WorkStates.choosing_action)
        await message.answer("Выберите действие:", reply_markup=ACTION_KEYBOARD)
    else:
        # На выборе участка — просто повторить
        await message.answer("Выберите участок:", reply_markup=SITE_KEYBOARD)


@dp.message(WorkStates.choosing_site, F.text.in_(SITES))
async def site_chosen(message: Message, state: FSMContext):
    await state.update_data(chosen_site=message.text)
    await state.set_state(WorkStates.choosing_action)
    await message.answer("Выберите действие:", reply_markup=ACTION_KEYBOARD)


@dp.message(WorkStates.choosing_action, F.text.in_(["Пришёл на работу", "Ушёл с работы"]))
async def action_chosen(message: Message, state: FSMContext):
    action = "Пришёл" if "Пришёл" in message.text else "Ушёл"
    await state.update_data(action=action)
    await state.set_state(WorkStates.awaiting_location)
    await message.answer("Отправьте геолокацию для подтверждения", reply_markup=LOCATION_KEYBOARD)


@dp.message(WorkStates.awaiting_location, F.content_type == ContentType.LOCATION)
async def handle_location(message: Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    action = data.get("action", "Пришёл")
    site = data.get("chosen_site", "Не указан")

    lat = message.location.latitude
    lon = message.location.longitude
    yandex_link = f"https://yandex.ru/maps/?pt={lon},{lat}&z=18"

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    now = datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")

    telegram_name = message.from_user.full_name
    canonical_name = KNOWN_EMPLOYEES.get(uid, telegram_name)

    try:
        log.append_row([now, uid, canonical_name, action, yandex_link, site])
        print(f"{action} — {canonical_name} — {site} — {now}")
    except Exception as e:
        print(f"Ошибка записи: {e}")
        await message.answer("Не удалось сохранить запись.")
        return

    await message.answer(
        f"{action} на участке <b>{site}</b>, зафиксировано ✅\n{now}",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="➕ Новое действие")]],
            resize_keyboard=True
        )
    )
    await state.clear()


@dp.message(F.text == "➕ Новое действие")
async def new_action(message: Message, state: FSMContext):
    await state.clear()
    await start(message, state)


@dp.message(F.text == "Отчёт: кто пришёл/ушёл")
async def report_attendance(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Доступ запрещён.")
        return

    moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")
    today = datetime.now(moscow_tz).strftime("%Y-%m-%d")

    try:
        records = log.get_all_records()
        today_records = [r for r in records if r.get("Дата/время", "").startswith(today)]

        if not today_records:
            await message.answer("Сегодня никто не отметился.")
            return

        came = []
        left = []
        for r in today_records:
            name = r.get("Имя", "—")
            action = r.get("Действие", "")
            time_str = r.get("Дата/время", "")[-8:]  # HH:MM:SS
            site = r.get("Участок", "")
            line = f"• {name} ({site}) — {time_str}"
            if action == "Пришёл":
                came.append(line)
            elif action == "Ушёл":
                left.append(line)

        lines = ["<b>Отчёт за сегодня:</b>"]

        if came:
            lines.append("\n<b>Пришли:</b>")
            lines.extend(came)
        else:
            lines.append("\n<b>Пришли:</b>\n— Никто")

        if left:
            lines.append("\n<b>Ушли:</b>")
            lines.extend(left)
        else:
            lines.append("\n<b>Ушли:</b>\n— Никто")

        await message.answer("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка отчёта: {e}")
        await message.answer("Не удалось сформировать отчёт.")


@dp.message(F.text == "Кто не отметился")
async def report_missing(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Доступ запрещён.")
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
            await message.answer("Все сотрудники отметились сегодня!")
        else:
            response = "<b>Не отметились сегодня:</b>\n" + "\n".join(missing)
            await message.answer(response, parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка 'не отметились': {e}")
        await message.answer("Ошибка при проверке неотметившихся.")


# === 6. Запуск ===
async def main():
    print("Бот запущен и ожидает сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен вручную")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
