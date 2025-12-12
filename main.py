import os
import sys
import json
import traceback
import math
import logging
from datetime import datetime, timedelta
import zoneinfo
import gspread
from gspread.exceptions import WorksheetNotFound, APIError
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ContentType, ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# === 1. Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_RAW = os.getenv("GOOGLE_CREDENTIALS")

ADMIN_USER_IDS = {653474435}  # Добавь других админов через запятую
def parse_admin_ids(raw_ids: str | None) -> set[int]:
    if not raw_ids:
        return set()
    ids: set[int] = set()
    for part in raw_ids.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logging.warning("Игнорирую некорректный tg_id администратора: %s", part)
    return ids


ADMIN_USER_IDS = parse_admin_ids(os.getenv("ADMIN_USER_IDS")) or {653474435}
KNOWN_EMPLOYEES = {
    467500951: "Хорошенин Сергей",
    653474435: "Рашидов Михаил",
    # Добавляй остальных: user_id: "Фамилия Имя"
}

SITES = ["Мичуринский", "Рязанский", "Зеленая Роща", "Калчуга"]

BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BACKUP_DIR, "bot.log"), encoding="utf-8"),
    ],
)

# === 2. Проверка переменных ===
missing = [v for v in ["BOT_TOKEN", "SHEET_ID", "GOOGLE_CREDENTIALS"] if not os.getenv(v)]
if missing:
    print(f"ОШИБКА: Не заданы переменные: {', '.join(missing)}")
    sys.exit(1)

# === 3. Google Sheets ===
try:
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SHEET_ID)

    # Лог отметок
    try:
        log = sh.worksheet("TimeLog")
    except WorksheetNotFound:
        log = sh.add_worksheet(title="TimeLog", rows=1000, cols=10)
        log.append_row(["Дата/время", "User ID", "Имя", "Действие", "Карта", "Участок"])

    # Соответствие: название в боте → точное название листа в таблице
    SITE_TO_SHEET = {
        "Мичуринский": "Мичуринский проспект 2",
        "Рязанский": "Рязанский проспект 39",
        "Зеленая Роща": "Зелёная Роща",
        "Калчуга": "Калчуга",
        # Добавь при необходимости
    }

    # Кэшируем листы объектов
    site_worksheets = {}
    for bot_name, sheet_name in SITE_TO_SHEET.items():
        try:
            site_worksheets[bot_name] = sh.worksheet(sheet_name)
            print(f"Подключен лист объекта: {sheet_name}")
        except WorksheetNotFound:
            print(f"ВНИМАНИЕ: Не найден лист: {sheet_name}")

    print("Google Sheets готов")
except Exception as e:
    print(f"Ошибка подключения к Google Sheets: {e}")
    traceback.print_exc()
    sys.exit(1)


def backup_spreadsheet():
    tz = zoneinfo.ZoneInfo("Europe/Moscow")
    timestamp = datetime.now(tz).strftime("%Y%m%d-%H%M%S")
    backup_files: list[str] = []

    for ws in sh.worksheets():
        try:
            values = ws.get_all_values()
            safe_title = ws.title.replace("/", "-")
            filename = os.path.join(BACKUP_DIR, f"{timestamp}-{safe_title}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(values, f, ensure_ascii=False, indent=2)
            backup_files.append(filename)
        except Exception as exc:  # noqa: BLE001
            logging.error("Ошибка бэкапа листа %s: %s", ws.title, exc)

    logging.info("Создан бэкап таблицы: %s", ", ".join(backup_files))
    return backup_files

# === 4. Бот ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class WorkStates(StatesGroup):
    choosing_site = State()
    choosing_action = State()
    awaiting_location = State()

# Клавиатуры
BACK_BUTTON = KeyboardButton(text="↩️ Назад")
SITE_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=s)] for s in SITES] + [[BACK_BUTTON]],
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
    keyboard=[[KeyboardButton(text="Отправить геолокацию", request_location=True)], [BACK_BUTTON]],
    resize_keyboard=True
)

# === 5. Вспомогательные ===
async def show_site_selection(message: Message, state: FSMContext):
    await state.set_state(WorkStates.choosing_site)
    await message.answer("Выберите объект:", reply_markup=SITE_KEYBOARD)


def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_USER_IDS:
        return True
    logging.warning("Запрет не-админу user_id=%s", user_id)
    return False


def log_action(user_id: int, action: str, details: str | None = None) -> None:
    extra = f"; {details}" if details else ""
    logging.info("user_id=%s: %s%s", user_id, action, extra)

# === 6. Хэндлеры ===
@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in ADMIN_USER_IDS:
    log_action(message.from_user.id, "Команда /start")
    if is_admin(message.from_user.id):
        admin_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Отчёт: кто пришёл/ушёл")],
                [KeyboardButton(text="Кто не отметился")],
                [KeyboardButton(text="Рассчитать вчерашний день")]
                [KeyboardButton(text="Рассчитать вчерашний день")],
                [KeyboardButton(text="Сделать бэкап")]
            ],
            resize_keyboard=True
        )
        await message.answer("Панель руководителя", reply_markup=admin_kb)
    else:
        await show_site_selection(message, state)

@dp.message(F.text == "↩️ Назад")
async def back_handler(message: Message, state: FSMContext):
    log_action(message.from_user.id, "Нажата кнопка Назад")
    current = await state.get_state()
    if current == WorkStates.awaiting_location.state:
        await state.set_state(WorkStates.choosing_action)
        await message.answer("Выберите действие:", reply_markup=ACTION_KEYBOARD)
    elif current == WorkStates.choosing_action.state:
        await show_site_selection(message, state)
    else:
        await show_site_selection(message, state)

@dp.message(WorkStates.choosing_site, F.text.in_(SITES))
async def site_selected(message: Message, state: FSMContext):
    log_action(message.from_user.id, "Выбор объекта", message.text)
    await state.update_data(site=message.text)
    await state.set_state(WorkStates.choosing_action)
    await message.answer("Выберите действие:", reply_markup=ACTION_KEYBOARD)

@dp.message(WorkStates.choosing_action, F.text.in_({"Пришёл на работу", "Ушёл с работы"}))
async def action_selected(message: Message, state: FSMContext):
    log_action(message.from_user.id, "Выбор действия", message.text)
    action = "Пришёл" if "Пришёл" in message.text else "Ушёл"
    await state.update_data(action=action)
    await state.set_state(WorkStates.awaiting_location)
    await message.answer("Отправьте геолокацию:", reply_markup=LOCATION_KEYBOARD)

@dp.message(WorkStates.awaiting_location, F.content_type == ContentType.LOCATION)
async def location_received(message: Message, state: FSMContext):
    data = await state.get_data()
    site = data.get("site", "Не указан")
    action = data.get("action", "Пришёл")

    lat = message.location.latitude
    lon = message.location.longitude
    map_link = f"https://yandex.ru/maps/?pt={lon},{lat}&z=18&l=map"

    tz = zoneinfo.ZoneInfo("Europe/Moscow")
    timestamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    user_id = message.from_user.id
    name = KNOWN_EMPLOYEES.get(user_id, message.from_user.full_name)

    log_action(user_id, "Получена геолокация", f"{action} — {site}")

    try:
        log.append_row([timestamp, user_id, name, action, map_link, site])
        logging.info("Записана отметка %s для %s (%s)", action, name, site)
    except Exception as e:
        await message.answer("Ошибка записи в лог.")
        print(e)
        return

    await message.answer(
        f"Зафиксировано: <b>{action} — {site}</b>\n{timestamp}\n<a href='{map_link}'>На карте</a>",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Новое действие")]], resize_keyboard=True),
        disable_web_page_preview=True
    )
    await state.clear()

@dp.message(F.text == "Новое действие")
async def new_action(message: Message, state: FSMContext):
    log_action(message.from_user.id, "Новое действие")
    await state.clear()
    await cmd_start(message, state)

# === Админские функции ===
@dp.message(F.text == "Рассчитать вчерашний день")
async def calculate_yesterday(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещён.")
    log_action(message.from_user.id, "Запрос расчёта за вчера")

    tz = zoneinfo.ZoneInfo("Europe/Moscow")
    target_date = (datetime.now(tz) - timedelta(days=1)).date()  # ВЧЕРА
    date_str = target_date.strftime("%d.%m.%Y")
    day_num = target_date.strftime("%-d")  # 1, 2, 3... без нуля

    await message.answer(f"Считаю часы за <b>{date_str}</b>...", parse_mode="HTML")

    try:
        records = log.get_all_records()
        day_records = [r for r in records if r.get("Дата/время", "").startswith(target_date.strftime("%Y-%m-%d"))]

        if not day_records:
            return await message.answer("Нет отметок за этот день.")

        from collections import defaultdict
        sessions = defaultdict(list)

        for r in day_records:
            name = r.get("Имя")
            site = r.get("Участок")
            action = r.get("Действие")
            dt_str = r.get("Дата/время")
            if not all([name, site, action, dt_str]): continue
            try:
@@ -243,52 +313,76 @@ async def calculate_yesterday(message: Message):
            # Ищем строку по фамилии или ФИО
            try:
                cell = sheet.find(name.split()[-1]) or sheet.find(name)
                if not cell:
                    continue
                row = cell.row

                # Ищем колонку с датой (в строке 3)
                header = sheet.row_values(3)
                col = next((i+1 for i, v in enumerate(header) if v.strip() in [day_num, target_date.strftime("%d")]), None)
                if not col:
                    continue

                sheet.update_cell(row, col, hours)
                updated += 1
            except Exception as e:
                print(f"Ошибка записи {name}: {e}")

        await message.answer(f"Готово!\nЗа {date_str} заполнено <b>{updated}</b> ячеек.", parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка расчёта: {e}")
        traceback.print_exc()
        await message.answer("Ошибка при расчёте.")


@dp.message(F.text == "Сделать бэкап")
async def handle_backup(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещён.")

    log_action(message.from_user.id, "Запрос бэкапа")
    await message.answer("Делаю резервную копию таблицы...")

    try:
        backup_files = backup_spreadsheet()
        if backup_files:
            await message.answer("Бэкап готов. Файлы сохранены локально на сервере.")
        else:
            await message.answer("Не удалось создать бэкап: нет доступных листов.")
    except Exception as exc:  # noqa: BLE001
        logging.error("Ошибка бэкапа: %s", exc)
        await message.answer("Ошибка при создании бэкапа.")

# Отчёты (по желанию оставь)
@dp.message(F.text == "Отчёт: кто пришёл/ушёл")
async def report_today(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS: return
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещён.")
    log_action(message.from_user.id, "Отчёт кто пришёл/ушёл")
    # (можно оставить старую реализацию)

@dp.message(F.text == "Кто не отметился")
async def missing_today(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS: return
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещён.")
    log_action(message.from_user.id, "Отчёт кто не отметился")
    # (можно оставить)

@dp.message()
async def unknown(message: Message, state: FSMContext):
    log_action(message.from_user.id, "Неизвестное сообщение", message.text or message.content_type)
    current = await state.get_state()
    if current:
        await message.answer("Пожалуйста, используйте кнопки.")
    else:
        await message.answer("Нажмите /start")

# === Запуск ===
async def main():
    print("Бот запущен и работает с твоими табелями по объектам!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
