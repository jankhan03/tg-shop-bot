# admin_bot/bot.py
import inspect
import asyncio
import os
import shutil
import uuid
from html import escape
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BotCommand, MenuButtonCommands
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from server.db import SessionLocal, engine, Base
from server.models import Product, ProductImage


ADMIN_IDS = set(settings.ADMIN_IDS)

# ---------- фиксированный список категорий (выбирается одна) ----------
CATEGORY_CHOICES = [
    "Кузовные части",
    "Освещение и блоки",
    "Навесные элементы",
    "Компоненты ДВС",
    "Система охлаждения",
    "Тормозная система",
    "Рулевое и подвески",
    "Колеса и диски",
    "Элементы салона",
    "Расходные материалы",
    "Аксессуары",
]


# ---------- утилиты для категорий ----------
def get_category_text(p: Product) -> str:
    """Безопасно получить категорию товара как строку."""
    # наша модель имеет Product.category (VARCHAR, NOT NULL, default='')
    val = getattr(p, "category", "") or ""
    return val if val.strip() else "—"


def category_kb(active: Optional[str] = None):
    """Клавиатура выбора одной категории."""
    kb = InlineKeyboardBuilder()
    for i, name in enumerate(CATEGORY_CHOICES):
        label = f"✅ {name}" if name == (active or "") else name
        kb.button(text=label, callback_data=f"cat_pick:{i}")
    kb.button(text="— Без категории", callback_data="cat_pick:-")
    kb.adjust(1)
    return kb.as_markup()


# ---------- меню-клавиатуры ----------
def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новый товар", callback_data="menu_new")
    kb.button(text="📋 Список", callback_data="menu_list")
    kb.button(text="🔍 Посмотреть", callback_data="menu_view")
    kb.button(text="🖼 Добавить фото", callback_data="menu_addphoto")
    kb.button(text="🗑 Удалить", callback_data="menu_del")
    if getattr(settings, "WEBAPP_URL", None):
        kb.button(text="🏪 Открыть магазин", url=settings.WEBAPP_URL)
    kb.adjust(1)
    return kb.as_markup()


def cancel_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🚫 Отмена", callback_data="menu_cancel")
    kb.adjust(1)
    return kb.as_markup()


# ---------- декоратор доступа ----------
def admin_only(handler):
    sig = inspect.signature(handler)
    allowed = set(sig.parameters.keys())

    async def wrapper(event, *args, **kwargs):
        from_user = getattr(event, "from_user", None) or getattr(
            getattr(event, "message", None), "from_user", None
        )
        user_id = from_user.id if from_user else None
        target = event.message if isinstance(event, CallbackQuery) else event
        if user_id not in ADMIN_IDS:
            await target.answer("Доступ запрещён.", parse_mode=None)
            if isinstance(event, CallbackQuery):
                await event.answer()
            return
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        return await handler(event, *args, **filtered_kwargs)

    return wrapper


# ---------- FSM ----------
class NewProduct(StatesGroup):
    title = State()
    price = State()
    subtitle = State()
    status = State()
    category = State()
    photos = State()


class AwaitID(StatesGroup):
    view_id = State()
    del_id = State()
    addphoto_id = State()


# ---------- Bot / Dispatcher ----------
bot = Bot(settings.ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


# ---------- helpers ----------
def product_dir(pid: int) -> str:
    return os.path.join(settings.MEDIA_ROOT, "products", str(pid))


async def add_image_record(s: AsyncSession, pid: int, relpath: str, order: int) -> ProductImage:
    img = ProductImage(product_id=pid, path=relpath, sort_order=order)
    s.add(img)
    await s.commit()
    await s.refresh(img)
    return img


async def setup_bot_ui():
    cmds = [
        BotCommand(command="start", description="Открыть меню"),
        BotCommand(command="menu", description="Показать меню"),
        BotCommand(command="new", description="Добавить товар"),
        BotCommand(command="list", description="Список товаров"),
        BotCommand(command="view", description="Посмотреть товар: /view id"),
        BotCommand(command="addphoto", description="Добавить фото: /addphoto id"),
        BotCommand(command="del", description="Удалить товар: /del id"),
        BotCommand(command="delphoto", description="Удалить фото: /delphoto pid image_id"),
    ]
    await bot.set_my_commands(cmds)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


# ---------- команды ----------
@dp.message(CommandStart())
@admin_only
async def start(m: Message):
    await m.answer(
        "Админ-панель. Выберите действие:",
        reply_markup=main_menu_kb(),
        parse_mode=None,
    )


@dp.message(Command("menu"))
@admin_only
async def menu_cmd(m: Message):
    await m.answer("Меню:", reply_markup=main_menu_kb(), parse_mode=None)


@dp.message(Command("list"))
@admin_only
async def list_(m: Message):
    async with SessionLocal() as s:
        res = await s.execute(select(Product).order_by(Product.id.desc()))
        items = res.scalars().all()
    if not items:
        await m.answer("Пусто.", parse_mode=None)
        return
    lines = []
    for p in items:
        cat = get_category_text(p)
        lines.append(f"#{p.id} — {p.title} — {p.price}₽ ({p.status}) [{cat}]")
    await m.answer("\n".join(lines), parse_mode=None)


@dp.message(Command("view"))
@admin_only
async def view_(m: Message):
    parts = (m.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await m.answer("Использование: /view [id]", parse_mode=None)
        return
    pid = int(parts[1])
    async with SessionLocal() as s:
        p = await s.get(Product, pid)
    if not p:
        await m.answer("Нет такого товара", parse_mode=None)
        return
    pics = sorted(p.images, key=lambda i: (i.sort_order, i.id))
    title = escape(p.title or "")
    subtitle = escape(p.subtitle or "")
    status = escape(p.status or "")
    cat = escape(get_category_text(p))
    msg = (
        f"<b>#{p.id}</b> {title}\n"
        f"{subtitle}\n{status}\n"
        f"Цена: {p.price}₽\n"
        f"Категория: {cat}\n"
        f"Фото: {[i.id for i in pics]}"
    )
    await m.answer(msg)


@dp.message(Command("del"))
@admin_only
async def del_(m: Message):
    parts = (m.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await m.answer("Использование: /del [id]", parse_mode=None)
        return
    pid = int(parts[1])
    async with SessionLocal() as s:
        obj = await s.get(Product, pid)
        if not obj:
            await m.answer("Нет такого товара", parse_mode=None)
            return
        await s.delete(obj)
        await s.commit()
    shutil.rmtree(product_dir(pid), ignore_errors=True)
    await m.answer(f"Удалено #{pid}", parse_mode=None)


@dp.message(Command("new"))
@admin_only
async def new_(m: Message, state: FSMContext):
    await state.set_state(NewProduct.title)
    await m.answer("Название?", parse_mode=None)


@dp.message(NewProduct.title)
@admin_only
async def new_title(m: Message, state: FSMContext):
    await state.update_data(title=(m.text or "").strip())
    await state.set_state(NewProduct.price)
    await m.answer("Цена (число)?", parse_mode=None)


@dp.message(NewProduct.price)
@admin_only
async def new_price(m: Message, state: FSMContext):
    try:
        price = float((m.text or "").replace(",", "."))
    except Exception:
        await m.answer("Нужно число. Введите цену ещё раз.", parse_mode=None)
        return
    await state.update_data(price=price)
    await state.set_state(NewProduct.subtitle)
    await m.answer("Короткое описание/подзаголовок?", parse_mode=None)


@dp.message(NewProduct.subtitle)
@admin_only
async def new_subtitle(m: Message, state: FSMContext):
    await state.update_data(subtitle=(m.text or "").strip())
    await state.set_state(NewProduct.status)
    await m.answer("Статус? (например: В наличии / В пути)", parse_mode=None)


@dp.message(NewProduct.status)
@admin_only
async def new_status(m: Message, state: FSMContext):
    await state.update_data(status=((m.text or "").strip() or "В наличии"))
    await state.set_state(NewProduct.category)
    await m.answer("Выберите категорию (одну):", reply_markup=category_kb(), parse_mode=None)


# Фоллбек: если админ вручную ввёл текст категории
@dp.message(NewProduct.category)
@admin_only
async def new_category_text(m: Message, state: FSMContext):
    picked = (m.text or "").strip()
    if picked in {"-", "—"}:
        picked = None
    await create_product_and_go_photos(m, state, picked)


@dp.callback_query(F.data.startswith("cat_pick:"))
@admin_only
async def cat_pick(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    code = cb.data.split(":", 1)[1]
    picked: Optional[str]
    if code == "-":
        picked = None
    else:
        try:
            idx = int(code)
            picked = CATEGORY_CHOICES[idx]
        except Exception:
            await cb.message.answer("Некорректный выбор категории.", parse_mode=None)
            return
    await create_product_and_go_photos(cb.message, state, picked)


async def create_product_and_go_photos(
    target_msg: Message, state: FSMContext, picked_category: Optional[str]
):
    data = await state.get_data()
    # СРАЗУ записываем категорию: пустая строка вместо None — чтобы не нарушать NOT NULL
    category_value = (picked_category or "").strip()
    async with SessionLocal() as s:
        p = Product(
            title=data["title"],
            price=data["price"],
            subtitle=data["subtitle"],
            status=data["status"],
            category=category_value,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        pid = p.id

    await state.update_data(product_id=pid, order=0)
    os.makedirs(product_dir(pid), exist_ok=True)
    await state.set_state(NewProduct.photos)
    cat_msg = picked_category or "—"
    await target_msg.answer(
        f"Товар #{pid} создан.\nКатегория: {cat_msg}\n"
        f"Пришлите 1..N фото (как обычные фото). Завершение — /done",
        parse_mode=None,
    )


@dp.message(Command("done"), NewProduct.photos)
@admin_only
async def done(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Готово. Товар сохранён.", parse_mode=None, reply_markup=main_menu_kb())


@dp.message(F.photo, NewProduct.photos)
@admin_only
async def add_photo_in_new(m: Message, state: FSMContext):
    data = await state.get_data()
    pid = data["product_id"]
    order = int(data.get("order", 0))

    dest_dir = product_dir(pid)
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    dest_path = os.path.join(dest_dir, filename)

    ph = m.photo[-1]
    await bot.download(ph, destination=dest_path)

    relpath = os.path.relpath(dest_path, settings.MEDIA_ROOT)
    async with SessionLocal() as s:
        await add_image_record(s, pid, relpath, order)

    await state.update_data(order=order + 1)
    await m.answer(f"Фото добавлено ({filename}). Ещё отправляйте или /done", parse_mode=None)


@dp.message(Command("addphoto"))
@admin_only
async def addphoto(m: Message, state: FSMContext):
    parts = (m.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await m.answer("Использование: /addphoto [id], затем пришлите фото", parse_mode=None)
        return
    pid = int(parts[1])
    await state.set_state(NewProduct.photos)
    await state.update_data(product_id=pid, order=0)
    os.makedirs(product_dir(pid), exist_ok=True)
    await m.answer(f"Ок. Жду фото для #{pid}. Завершение — /done", parse_mode=None)


@dp.message(Command("delphoto"))
@admin_only
async def delphoto(m: Message):
    parts = (m.text or "").strip().split()
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await m.answer("Использование: /delphoto [product_id] [image_id]", parse_mode=None)
        return
    pid = int(parts[1])
    img_id = int(parts[2])
    async with SessionLocal() as s:
        img = await s.get(ProductImage, img_id)
        if not img or img.product_id != pid:
            await m.answer("Нет такого фото", parse_mode=None)
            return
        abs_path = os.path.join(settings.MEDIA_ROOT, img.path)
        try:
            os.remove(abs_path)
        except FileNotFoundError:
            pass
        await s.delete(img)
        await s.commit()
    await m.answer(f"Фото {img_id} удалено.", parse_mode=None)


# ---------- кнопочное меню ----------
@dp.callback_query(F.data == "menu_new")
@admin_only
async def cb_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(NewProduct.title)
    await cb.message.answer("Название?", parse_mode=None, reply_markup=cancel_menu_kb())


@dp.callback_query(F.data == "menu_list")
@admin_only
async def cb_list(cb: CallbackQuery):
    await cb.answer()
    async with SessionLocal() as s:
        res = await s.execute(select(Product).order_by(Product.id.desc()))
        items = res.scalars().all()
    if not items:
        await cb.message.answer("Пусто.", parse_mode=None)
        return
    lines = []
    for p in items:
        cat = get_category_text(p)
        lines.append(f"#{p.id} — {p.title} — {p.price}₽ ({p.status}) [{cat}]")
    await cb.message.answer("\n".join(lines), parse_mode=None)


@dp.callback_query(F.data == "menu_view")
@admin_only
async def cb_view(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AwaitID.view_id)
    await cb.message.answer("Введите ID товара:", parse_mode=None, reply_markup=cancel_menu_kb())


@dp.callback_query(F.data == "menu_del")
@admin_only
async def cb_del(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AwaitID.del_id)
    await cb.message.answer("Введите ID товара для удаления:", parse_mode=None, reply_markup=cancel_menu_kb())


@dp.callback_query(F.data == "menu_addphoto")
@admin_only
async def cb_addphoto(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AwaitID.addphoto_id)
    await cb.message.answer("Введите ID товара, к которому добавить фото:", parse_mode=None, reply_markup=cancel_menu_kb())


@dp.callback_query(F.data == "menu_cancel")
@admin_only
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Отмена")
    await state.clear()
    await cb.message.answer("Отменено.", parse_mode=None, reply_markup=main_menu_kb())


@dp.message(AwaitID.view_id)
@admin_only
async def id_view_flow(m: Message, state: FSMContext):
    if not (m.text or "").isdigit():
        await m.answer("Нужен числовой ID.", parse_mode=None)
        return
    pid = int(m.text)
    async with SessionLocal() as s:
        p = await s.get(Product, pid)
    if not p:
        await m.answer("Нет такого товара", parse_mode=None)
        return
    pics = sorted(p.images, key=lambda i: (i.sort_order, i.id))
    title = escape(p.title or "")
    subtitle = escape(p.subtitle or "")
    status = escape(p.status or "")
    cat = escape(get_category_text(p))
    await m.answer(
        f"<b>#{p.id}</b> {title}\n{subtitle}\n{status}\n"
        f"Цена: {p.price}₽\nКатегория: {cat}\n"
        f"Фото: {[i.id for i in pics]}",
        parse_mode="HTML",
    )
    await state.clear()
    await m.answer("Готово.", parse_mode=None, reply_markup=main_menu_kb())


@dp.message(AwaitID.del_id)
@admin_only
async def id_del_flow(m: Message, state: FSMContext):
    if not (m.text or "").isdigit():
        await m.answer("Нужен числовой ID.", parse_mode=None)
        return
    pid = int(m.text)
    async with SessionLocal() as s:
        obj = await s.get(Product, pid)
        if not obj:
            await m.answer("Нет такого товара", parse_mode=None)
            return
        await s.delete(obj)
        await s.commit()
    shutil.rmtree(product_dir(pid), ignore_errors=True)
    await m.answer(f"Удалено #{pid}", parse_mode=None)
    await state.clear()
    await m.answer("Готово.", parse_mode=None, reply_markup=main_menu_kb())


@dp.message(AwaitID.addphoto_id)
@admin_only
async def id_addphoto_flow(m: Message, state: FSMContext):
    if not (m.text or "").isdigit():
        await m.answer("Нужен числовой ID.", parse_mode=None)
        return
    pid = int(m.text)
    os.makedirs(product_dir(pid), exist_ok=True)
    await state.set_state(NewProduct.photos)
    await state.update_data(product_id=pid, order=0)
    await m.answer(f"Ок. Жду фото для #{pid}. Завершение — /done", parse_mode=None)


# ---------- entry point ----------
async def main():
    if not settings.ADMIN_BOT_TOKEN:
        raise RuntimeError("Нужен ADMIN_BOT_TOKEN")

    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await setup_bot_ui()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
