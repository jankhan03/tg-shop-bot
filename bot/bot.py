# bot/bot.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Message
)
from aiogram.client.default import DefaultBotProperties

from config import settings

bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    # убираем любые старые reply-клавиатуры
    await m.answer("...", reply_markup=ReplyKeyboardRemove())
    # отдаём кнопку с мини-аппом
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
