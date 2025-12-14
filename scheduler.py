import datetime as dt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from .db import SessionLocal
from .models import Employee, Attendance
from .config import settings
from .bot import bot_send_message
from .excel import write_day_mark
from pathlib import Path
from .mailer import send_file

WORKBOOK_PATH = Path("/app/data/timesheet_2025.xlsx")  # в Railway примонтируем volume

def ceil_hours_cap8(minutes: int) -> int:
    if minutes <= 0:
        return 0
    h = (minutes + 59) // 60
    return min(h, 8)

async def morning_reminder():
    today = dt.datetime.now(dt.timezone.utc).astimezone().date()
    with SessionLocal() as db:
        emps = db.execute(select(Employee).where(Employee.active == True, Employee.role == "employee")).scalars().all()
        for e in emps:
            att = db.execute(select(Attendance).where(Attendance.date==today, Attendance.employee_id==e.id)).scalar_one_or_none()
            if not att or not att.check_in:
                await bot_send_message(e.telegram_id, "⏰ Напоминание: отметьтесь о приходе (🟢 Пришёл)")

async def evening_reminder():
    today = dt.datetime.now(dt.timezone.utc).astimezone().date()
    with SessionLocal() as db:
        emps = db.execute(select(Employee).where(Employee.active == True, Employee.role == "employee")).scalars().all()
        for e in emps:
            att = db.execute(select(Attendance).where(Attendance.date==today, Attendance.employee_id==e.id)).scalar_one_or_none()
            if att and att.check_in and not att.check_out and att.status != "SICK":
                await bot_send_message(e.telegram_id, "⏰ Напоминание: не забудьте отметить уход (🔴 Ушёл)")

async def auto_close_day():
    now = dt.datetime.now(dt.timezone.utc).astimezone()
    today = now.date()
    close_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
    with SessionLocal() as db:
        rows = db.execute(select(Attendance).where(Attendance.date==today)).scalars().all()
        for a in rows:
            if a.check_in and not a.check_out and a.status != "SICK":
                a.check_out = close_time
                minutes = int((a.check_out - a.check_in).total_seconds() // 60)
                a.minutes_worked = minutes
                a.hours_for_timesheet = ceil_hours_cap8(minutes)
                db.add(a)
        db.commit()

def last_day_of_month(d: dt.date) -> bool:
    return (d + dt.timedelta(days=1)).month != d.month

async def send_timesheet_if_due():
    now = dt.datetime.now(dt.timezone.utc).astimezone()
    d = now.date()
    if d.day not in (15,) and not last_day_of_month(d):
        return
    # просто отправляем файл
    send_file(
        subject=f"Табель {d.strftime('%Y-%m-%d')}",
        body="Автоматическая отправка табеля.",
        file_path=WORKBOOK_PATH
    )

def create_scheduler() -> AsyncIOScheduler:
    sch = AsyncIOScheduler(timezone=settings.TZ)
    sch.add_job(morning_reminder, CronTrigger(hour=9, minute=15))
    sch.add_job(evening_reminder, CronTrigger(hour=17, minute=45))
    sch.add_job(auto_close_day,   CronTrigger(hour=18, minute=30))
    sch.add_job(send_timesheet_if_due, CronTrigger(hour=12, minute=0))
    return sch
