from typing import List
from enum import Enum
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Boolean, func, Column, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(64), default="В наличии")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # делаем NOT NULL + дефолт пустая строка, чтобы ORM не вставлял NULL
    category: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    images: Mapped[List["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship("Product", back_populates="images")


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    mobile_number = Column(String(20))
    username = Column(String(50))
    name = Column(String(100))
    first_entry = Column(
        DateTime(timezone=True),
        default=func.now(),
    )


class UserLog(Base):
    __tablename__ = "user_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    action = Column(String(50))
    datetime = Column(
        DateTime(timezone=True),
        default=func.now(),
    )


class UserLogAction(Enum):
    WEB_APP_OPENED = "web_app_opened"
