# bot/bot.py
import asyncio
from sqlalchemy import select
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Message
)
from aiogram.client.default import DefaultBotProperties

from config import settings
from server.db import SessionLocal
from server.models import User

bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


async def user_exists(
    user_id: int,
):
    async with SessionLocal() as session:
        select_query = select(User).filter(User.id == user_id)
        result = await session.execute(select_query)
        user = result.scalar_one_or_none()
        return user is not None


async def save_user(
    user: User,
) -> User:
    async with SessionLocal() as db:
        if not await user_exists(user_id=user.id):
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user


@dp.message(CommandStart())
async def start(m: Message):
    await save_user(
        user=User(
            id=m.from_user.id,
            username=m.from_user.username,
            name=m.from_user.first_name,
        )
    )

    await m.answer("...", reply_markup=ReplyKeyboardRemove())

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🛍️ Открыть магазин",
            web_app=WebAppInfo(url=settings.WEBAPP_URL)
        )
    ]])
    await m.answer("Пожалуйста, выберите раздел, который вас интересует", reply_markup=kb)

async def main():
    if not settings.BOT_TOKEN or not settings.WEBAPP_URL:
        raise RuntimeError("Нужны BOT_TOKEN и WEBAPP_URL в .env")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
