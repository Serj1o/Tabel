import datetime as dt
from sqlalchemy import String, Integer, Boolean, Date, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db import Base

class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    patronymic: Mapped[str] = mapped_column(String(100), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(20), default="employee")  # admin/employee

    def fio(self) -> str:
        return " ".join([self.last_name, self.first_name, self.patronymic]).strip()

class ObjectSite(Base):
    __tablename__ = "objects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[int] = mapped_column(Integer, default=200)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Invite(Base):
    __tablename__ = "invites"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="employee")
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)

class Attendance(Base):
    __tablename__ = "attendance"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    object_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id"), nullable=True)

    check_in: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    check_out: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(String(10), default="OK")  # OK / SICK
    minutes_worked: Mapped[int] = mapped_column(Integer, default=0)
    hours_for_timesheet: Mapped[int] = mapped_column(Integer, default=0)

    employee: Mapped[Employee] = relationship()
    obj: Mapped[ObjectSite] = relationship()

    __table_args__ = (
        UniqueConstraint("date", "employee_id", name="uq_attendance_day"),
    )
