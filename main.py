from fastapi import FastAPI, Request, Header, HTTPException
from aiogram.types import Update
from bot import dp, bot
from config import settings
from db import engine, Base
from scheduler import create_scheduler

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    Base.metadata.create_all(engine)
    # set webhook
    webhook_url = f"{settings.BASE_URL}/telegram/{settings.WEBHOOK_SECRET}"
    await bot.set_webhook(webhook_url)

    # scheduler
    sch = create_scheduler()
    sch.start()

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()

@app.post("/telegram/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=404)
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "ok"}
