from typing import List, Optional, Dict
import json, hmac, hashlib, urllib.parse
from bot.bot import get_user
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from config import settings
from server.db import SessionLocal, get_session
from server.models import Product, UserLog, UserLogAction

app = FastAPI()

# ---- статика ----
#app.mount("/webapp", StaticFiles(directory="webapp", html=True), name="webapp")
app.mount("/media", StaticFiles(directory=settings.MEDIA_ROOT), name="media")

# ---- фиксированный список (для сортировки выдачи /api/categories) ----
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

# ---- утилиты ----
def rub(x) -> str:
    try:
        return f"{int(round(float(x))):,} ₽".replace(",", " ")
    except Exception:
        return f"{x} ₽"


def parse_telegram_init_data(init_data: str, bot_token: str):
    if not init_data:
        return None, False
    data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", "")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    check_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    is_valid = hmac.compare_digest(check_hash, received_hash)

    user = None
    if "user" in data:
        try:
            user = json.loads(data["user"])
        except Exception:
            user = None
    return user, is_valid


def _img_url(request: Request, relpath: str) -> str:
    return str(request.url_for("media", path=relpath))


# ---- схемы ответа ----
class ProductOut(BaseModel):
    id: int
    title: str
    price: float
    subtitle: str
    status: str
    image: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)  # одна категория -> список из одного элемента

    class Config:
        orm_mode = True


class CategoryOut(BaseModel):
    name: str
    count: int


class WebAppUser(BaseModel):
    id: int
    is_bot: Optional[bool] = None
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = None


def _map_product(request: Request, p: Product) -> ProductOut:
    imgs = sorted(p.images or [], key=lambda i: (i.sort_order, i.id))
    urls = [_img_url(request, i.path) for i in imgs]
    cats = [p.category] if getattr(p, "category", None) else []
    return ProductOut(
        id=p.id,
        title=p.title or "",
        price=float(p.price or 0),
        subtitle=p.subtitle or "",
        status=p.status or "",
        image=(urls[0] if urls else None),
        images=urls,
        categories=cats,
    )


# ---- health ----
@app.get("/health")
async def health(s: AsyncSession = Depends(get_session)):
    await s.execute(text("SELECT 1"))
    return {"status": "ok"}


# ---- каталог ----
@app.get("/api/products", response_model=List[ProductOut])
async def products(
    request: Request,
    q: Optional[str] = None,
    sort: Optional[str] = None,
    category: Optional[str] = None,  # фильтр по названию категории
    s: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.is_active == True)
        .order_by(Product.id.desc())
    )
    res = (await s.execute(stmt)).scalars().unique().all()

    items = res

    # Поиск
    if q:
        ql = q.lower()
        items = [p for p in items if ql in (p.title or "").lower() or ql in (p.subtitle or "").lower()]

    # Фильтр по категории
    if category:
        want = category.strip().lower()
        items = [p for p in items if (getattr(p, "category", "") or "").strip().lower() == want]

    # Сортировка
    if sort == "price_asc":
        items = sorted(items, key=lambda x: (x.price or 0))
    elif sort == "price_desc":
        items = sorted(items, key=lambda x: (x.price or 0), reverse=True)

    return [_map_product(request, p) for p in items]


@app.get("/api/products/{pid}", response_model=ProductOut)
async def get_product(pid: int, request: Request, s: AsyncSession = Depends(get_session)):
    p = await s.get(Product, pid, options=(selectinload(Product.images),))
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return _map_product(request, p)


@app.get("/api/categories", response_model=List[CategoryOut])
async def categories(s: AsyncSession = Depends(get_session)):
    """Список категорий с количеством активных товаров (count>0)."""
    stmt = select(Product).where(Product.is_active == True)
    res = (await s.execute(stmt)).scalars().unique().all()
    counts: Dict[str, int] = {}
    for p in res:
        c = (getattr(p, "category", "") or "").strip()
        if not c:
            continue
        counts[c] = counts.get(c, 0) + 1

    out: List[CategoryOut] = []
    seen = set()
    # сначала известные (в заданном порядке)
    for name in CATEGORY_CHOICES:
        if counts.get(name):
            out.append(CategoryOut(name=name, count=counts[name]))
            seen.add(name)
    # потом все прочие, если появятся
    for name, cnt in sorted(counts.items()):
        if name not in seen:
            out.append(CategoryOut(name=name, count=cnt))
    return out


@app.post("/api/webapp-opened")
async def webapp_opened(
    user_data: WebAppUser,
):
    # Get user
    db_user = await get_user(
        id=user_data.id,
    )
    user_log = UserLog(
        user_id=db_user.id,
        action=UserLogAction.WEB_APP_OPENED.value,
    )
    async with SessionLocal() as db:
        db.add(user_log)
        await db.commit()
        await db.refresh(user_log)

    return {"status": "ok"}


# ---- приём заказа и пересылка в TG ----
@app.post("/api/submit_cart")
async def submit_cart(req: Request):
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "empty cart")

    init_data = body.get("init_data") or ""
    user, valid = parse_telegram_init_data(init_data, settings.BOT_TOKEN)

    contact = body.get("contact") or {}
    name = str(contact.get("name") or "").strip()
    phone = str(contact.get("phone") or "").strip()
    tg_at = str(contact.get("tg") or contact.get("telegram") or "").strip().lstrip("@")
    if not user and not (phone or tg_at):
        raise HTTPException(400, detail="contact_required")

    lines = ["🧺 <b>Новый заказ</b>"]
    if user:
        uid = user.get("id")
        full = " ".join([user.get("first_name") or "", user.get("last_name") or ""]).strip() or "Покупатель"
        uname = ("@" + user.get("username")) if user.get("username") else "—"
        buyer_link = f'<a href="tg://user?id={uid}">{full}</a>'
        lines += [f"Покупатель: {buyer_link}", f"Username: {uname}", f"User ID: <code>{uid}</code>"]
        if not valid:
            lines.append("(⚠️ initData не прошло верификацию)")
    else:
        lines.append("Покупатель: неизвестно (мини-апп открыт вне Telegram)")

    if name or phone or tg_at:
        lines += ["", "<b>Контакты:</b>"]
        if name:
            lines.append(f"• Имя: {name}")
        if phone:
            lines.append(f"• Телефон: {phone}")
        if tg_at:
            lines.append(f"• Telegram: @{tg_at}")

    lines += ["", "<b>Товары:</b>"]
    total = 0.0
    for i, it in enumerate(items, 1):
        title = str(it.get("title") or "")
        qty = int(it.get("qty") or 0)
        price = float(it.get("price") or 0)
        subtotal = qty * price
        total += subtotal

        lines.append(f"<b>#{i}</b> {title}")
        lines.append(f"• Кол-во: {qty}")
        lines.append(f"• Цена: {rub(price)}")
        lines.append(f"• Сумма: {rub(subtotal)}")

        cats = it.get("categories") or []
        if isinstance(cats, (list, tuple)) and cats:
            lines.append("• Категория: " + ", ".join(map(str, cats)))

        for k, v in it.items():
            if k in {"title", "qty", "price", "image", "images", "categories"} or v in (None, ""):
                continue
            lines.append(f"• {k}: {v}")
        lines.append("")

    front_total = body.get("total")
    lines.append(f"<b>Итого:</b> {rub(total)}")
    try:
        if front_total is not None and abs(float(front_total) - total) > 0.01:
            lines.append(f"(из фронта: {rub(front_total)})")
    except Exception:
        pass

    text_msg = "\n".join(lines)

    seller_id = int(getattr(settings, "SELLER_CHAT_ID", 0) or 0)
    if not getattr(settings, "BOT_TOKEN", None) or not seller_id:
        raise HTTPException(500, "Bot configuration is invalid")

    async with Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML")) as tgbot:
        try:
            await tgbot.send_message(seller_id, text_msg, disable_web_page_preview=True)
        except TelegramForbiddenError:
            raise HTTPException(403, "Bot cannot message SELLER_CHAT_ID (no /start or blocked)")
        except TelegramBadRequest as e:
            raise HTTPException(400, f"Telegram BadRequest: {e}")
        except TelegramNetworkError as e:
            raise HTTPException(502, f"Telegram network error: {e}")
        except Exception as e:
            raise HTTPException(500, f"Unexpected error: {e}")

    return {"ok": True}
