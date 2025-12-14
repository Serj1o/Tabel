import datetime as dt
import secrets
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import CommandStart
from sqlalchemy import select
from config import settings
from db import SessionLocal
from models import Employee, Invite, ObjectSite, Attendance
from geo import haversine_m
from excel import ensure_year_workbook, write_day_mark
from pathlib import Path

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

WORKBOOK_PATH = Path("/app/data/timesheet_2025.xlsx")  # Railway Volume

def ceil_hours_cap8(minutes: int) -> int:
    if minutes <= 0:
        return 0
    return min((minutes + 59)//60, 8)

async def bot_send_message(chat_id: int, text: str):
    await bot.send_message(chat_id, text)

def main_kb(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🟢 Пришёл"), KeyboardButton(text="🔴 Ушёл")],
        [KeyboardButton(text="🤒 Болел")]
    ]
    if is_admin:
        rows.append([KeyboardButton(text="📍 Кто пришёл сегодня"), KeyboardButton(text="➕ Пригласить сотрудника")])
        rows.append([KeyboardButton(text="🏢 Объекты")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def require_user(telegram_id: int) -> Employee | None:
    with SessionLocal() as db:
        return db.execute(select(Employee).where(Employee.telegram_id==telegram_id, Employee.active==True)).scalar_one_or_none()

@dp.message(CommandStart())
async def start(m: Message):
    tid = m.from_user.id
    args = (m.text or "").split(maxsplit=1)
    token = args[1].strip() if len(args) > 1 else None

    with SessionLocal() as db:
        user = db.execute(select(Employee).where(Employee.telegram_id==tid)).scalar_one_or_none()

        # invite flow
        if not user and token:
            inv = db.execute(select(Invite).where(Invite.token==token, Invite.used==False)).scalar_one_or_none()
            if inv and inv.expires_at > dt.datetime.now(dt.timezone.utc):
                # create employee with unknown fio (admin will fill later)
                emp = Employee(telegram_id=tid, last_name=m.from_user.first_name or "Сотрудник", first_name="", patronymic="", role=inv.role, active=True)
                inv.used = True
                db.add_all([emp, inv])
                db.commit()
                await m.answer("✅ Вы добавлены. Напишите админу, чтобы он указал ФИО.", reply_markup=main_kb(inv.role=="admin"))
                return

        if not user or not user.active:
            await m.answer("⛔ Доступ запрещён. Обратитесь к администратору.")
            return

        await m.answer(f"Здравствуйте, {user.fio()} 👋", reply_markup=main_kb(user.role=="admin"))

@dp.message(F.text == "🟢 Пришёл")
async def check_in(m: Message):
    tid = m.from_user.id
    user = require_user(tid)
    if not user:
        return await m.answer("⛔ Нет доступа")

    # Ask location
    await m.answer("Отправьте геолокацию (скрепка → Геопозиция).")

@dp.message(F.location)
async def got_location(m: Message):
    tid = m.from_user.id
    user = require_user(tid)
    if not user:
        return await m.answer("⛔ Нет доступа")

    lat = m.location.latitude
    lon = m.location.longitude
    today = dt.datetime.now(dt.timezone.utc).astimezone().date()
    now = dt.datetime.now(dt.timezone.utc).astimezone()

    ensure_year_workbook(WORKBOOK_PATH, today.year)

    with SessionLocal() as db:
        # one record per day
        att = db.execute(select(Attendance).where(Attendance.date==today, Attendance.employee_id==user.id)).scalar_one_or_none()
        if att and (att.check_in or att.status == "SICK"):
            return await m.answer("❗ Вы уже отметились сегодня.")

        # choose nearest active object in radius
        objs = db.execute(select(ObjectSite).where(ObjectSite.active==True)).scalars().all()
        if not objs:
            return await m.answer("❗ Нет активных объектов. Сообщите администратору.")

        best = None
        for o in objs:
            dist = haversine_m(lat, lon, o.lat, o.lon)
            if dist <= o.radius_m:
                if best is None or dist < best[0]:
                    best = (dist, o)

        if not best:
            return await m.answer("⛔ Вы вне зоны объектов. Приход не засчитан.")

        obj = best[1]
        if not att:
            att = Attendance(date=today, employee_id=user.id, object_id=obj.id, check_in=now, status="OK")
        else:
            att.object_id = obj.id
            att.check_in = now
            att.status = "OK"

        db.add(att)
        db.commit()

    await m.answer(f"✅ Приход зафиксирован.\nОбъект: {obj.name}\nВремя: {now.strftime('%H:%M')}\n\nКогда уйдёте — нажмите 🔴 Ушёл.")

@dp.message(F.text == "🔴 Ушёл")
async def check_out(m: Message):
    tid = m.from_user.id
    user = require_user(tid)
    if not user:
        return await m.answer("⛔ Нет доступа")

    today = dt.datetime.now(dt.timezone.utc).astimezone().date()
    now = dt.datetime.now(dt.timezone.utc).astimezone()

    with SessionLocal() as db:
        att = db.execute(select(Attendance).where(Attendance.date==today, Attendance.employee_id==user.id)).scalar_one_or_none()
        if not att or not att.check_in:
            return await m.answer("❗ Нельзя отметить уход без прихода.")
        if att.status == "SICK":
            return await m.answer("❗ Сегодня отмечено как 'Болел'.")
        if att.check_out:
            return await m.answer("❗ Уход уже был отмечен сегодня.")

        att.check_out = now
        minutes = int((att.check_out - att.check_in).total_seconds() // 60)
        att.minutes_worked = minutes
        att.hours_for_timesheet = ceil_hours_cap8(minutes)
        db.add(att)
        db.commit()

    # write to Excel: day mark is hours capped at 8
    write_day_mark(WORKBOOK_PATH, today, user.fio(), att.hours_for_timesheet)

    await m.answer(f"✅ Уход зафиксирован.\nОтработано: {minutes//60}ч {minutes%60}м\nВ табель: {att.hours_for_timesheet} ч (округление вверх, максимум 8)")

@dp.message(F.text == "🤒 Болел")
async def sick(m: Message):
    tid = m.from_user.id
    user = require_user(tid)
    if not user:
        return await m.answer("⛔ Нет доступа")

    today = dt.datetime.now(dt.timezone.utc).astimezone().date()

    with SessionLocal() as db:
        att = db.execute(select(Attendance).where(Attendance.date==today, Attendance.employee_id==user.id)).scalar_one_or_none()
        if att and (att.check_in or att.check_out):
            return await m.answer("❗ Уже есть приход/уход сегодня. 'Болел' поставить нельзя.")
        if not att:
            att = Attendance(date=today, employee_id=user.id, status="SICK")
        else:
            att.status = "SICK"
        att.hours_for_timesheet = 0
        db.add(att)
        db.commit()

    write_day_mark(WORKBOOK_PATH, today, user.fio(), "Б")
    await m.answer("✅ Отмечено: Болел (Б)")

# --- Admin commands ---
def require_admin(tid: int) -> Employee | None:
    u = require_user(tid)
    return u if u and u.role == "admin" else None

@dp.message(F.text == "➕ Пригласить сотрудника")
async def invite(m: Message):
    admin = require_admin(m.from_user.id)
    if not admin:
        return await m.answer("⛔ Только для администратора")

    token = secrets.token_urlsafe(16)
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)

    with SessionLocal() as db:
        db.add(Invite(token=token, role="employee", expires_at=expires, used=False))
        db.commit()

    link = f"https://t.me/{(await bot.get_me()).username}?start={token}"
    await m.answer(f"Ссылка-приглашение (7 дней, одноразовая):\n{link}")

@dp.message(F.text == "📍 Кто пришёл сегодня")
async def who_today(m: Message):
    admin = require_admin(m.from_user.id)
    if not admin:
        return await m.answer("⛔ Только для администратора")

    today = dt.datetime.now(dt.timezone.utc).astimezone().date()
    with SessionLocal() as db:
        emps = db.execute(select(Employee).where(Employee.active==True, Employee.role=="employee")).scalars().all()
        lines = []
        for e in emps:
            att = db.execute(select(Attendance).where(Attendance.date==today, Attendance.employee_id==e.id)).scalar_one_or_none()
            if att and att.check_in and not att.check_out and att.status=="OK":
                lines.append(f"🟢 {e.fio()} — на работе")
            elif att and att.status=="SICK":
                lines.append(f"🤒 {e.fio()} — Б")
            elif att and att.check_out:
                lines.append(f"✅ {e.fio()} — ушёл")
            else:
                lines.append(f"🔴 {e.fio()} — не отметился")
    await m.answer("\n".join(lines))
