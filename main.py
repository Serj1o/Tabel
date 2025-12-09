import os
import json
import gspread
import traceback  # ← добавь это

# ... другие импорты ...

# === Проверка переменных ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_RAW = os.getenv("GOOGLE_CREDENTIALS")

if not all([BOT_TOKEN, SHEET_ID, GOOGLE_CREDENTIALS_RAW]):
    missing = [v for v in ["BOT_TOKEN", "SHEET_ID", "GOOGLE_CREDENTIALS"] if not os.getenv(v)]
    raise SystemExit(f"Не заданы переменные: {missing}")

# === Подключение к Google Sheets с ПОЛНЫМ логом ошибки ===
try:
    creds = json.loads(GOOGLE_CREDENTIALS_RAW)
    gc = gspread.service_account_from_dict(creds)
    print(f"✅ Авторизовались в Google с аккаунтом: {creds.get('client_email')}")
    
    print(f"📂 Открываем таблицу с ID: {SHEET_ID}")
    sh = gc.open_by_key(SHEET_ID)
    print(f"✅ Успешно открыта таблица: {sh.title}")
    
    print("📄 Ищем лист 'TimeLog'...")
    log = sh.worksheet("TimeLog")
    print("✅ Лист 'TimeLog' найден")

except Exception as e:
    print("🔴 ПОЛНАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К GOOGLE SHEETS:")
    traceback.print_exc()  # ← ЭТО ПОКАЖЕТ НАСТОЯЩУЮ ПРИЧИНУ
    raise SystemExit("Не удалось инициализировать Google Sheets")
