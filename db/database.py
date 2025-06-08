from datetime import timedelta
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    Text, ForeignKey, DateTime, JSON, DECIMAL
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

engine = create_engine("sqlite:///db/photoexpress.sqlite", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, index=True)
    telegram_id      = Column(Integer, unique=True, nullable=False)
    username         = Column(String)
    phone_number     = Column(String)
    full_name        = Column(String)
    accepted_policy  = Column(Boolean, default=False)
    # Новое поле: флаг, указывающий, что первый заказ уже был оплачен
    first_order_paid = Column(Boolean, default=False)

    created_at       = Column(DateTime, default=datetime.utcnow)


class OrderStatus(Base):
    __tablename__ = "order_statuses"

    code       = Column(String, primary_key=True)
    label      = Column(String)
    sort_order = Column(Integer)


class Order(Base):
    __tablename__ = "orders"

    order_id       = Column(String, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"))
    photos         = Column(JSON)
    delivery_point = Column(String)
    receiver_name  = Column(String)
    receiver_phone = Column(String)
    comment        = Column(Text)
    status         = Column(String, ForeignKey("order_statuses.code"), default="new")
    price          = Column(DECIMAL)
    discount       = Column(DECIMAL, default=0.0)
    paid           = Column(Boolean, default=False)
    created_at     = Column(DateTime, default=datetime.utcnow)


class PickupPoint(Base):
    __tablename__ = "pickup_points"

    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String, nullable=False)
    address  = Column(String)
    lat      = Column(DECIMAL)
    lon      = Column(DECIMAL)
    rating   = Column(DECIMAL)


# Новая таблица для хранения информации о промокодах
class PromoCode(Base):
    __tablename__ = "promo_codes"

    id               = Column(Integer, primary_key=True, index=True)
    code             = Column(String, unique=True, nullable=False)      # текст промокода
    discount_percent = Column(Integer, nullable=False)                  # процент скидки (например, 10, 20, 30 и т.д.)
    expires_at       = Column(DateTime, nullable=False)                 # дата и время истечения
    uses_left        = Column(Integer, nullable=True)                   # сколько раз ещё можно использовать (None = неограниченно)


def init_db():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    # Статусы заказов
    if not db.query(OrderStatus).first():
        default_statuses = [
            OrderStatus(code="new",        label="🔄 Новый",       sort_order=1),
            OrderStatus(code="in_progress",label="🛠 В обработке", sort_order=2),
            OrderStatus(code="completed",  label="✅ Готов",       sort_order=3),
            OrderStatus(code="cancelled",  label="❌ Отменён",     sort_order=4),
        ]
        db.add_all(default_statuses)

    # Пункты выдачи (Москва)
    if not db.query(PickupPoint).first():
        default_points = [
            PickupPoint(name="ПВЗ Тверская",          address="Тверская, 10",      lat=55.765, lon=37.610, rating=4.5),
            PickupPoint(name="ПВЗ Арбат",             address="Арбат, 25",         lat=55.752, lon=37.592, rating=4.2),
            PickupPoint(name="ПВЗ Пресненская наб.",   address="Пресненская наб., 8",lat=55.752, lon=37.590, rating=4.7),
            PickupPoint(name="ПВЗ Кутузовская",        address="Кутузовский пр., 30",lat=55.743, lon=37.553, rating=4.3),
            PickupPoint(name="ПВЗ Измайлово",          address="Измайловское ш., 71",lat=55.796, lon=37.762, rating=4.6),
        ]
        db.add_all(default_points)

    if not db.query(PromoCode).first():
        now = datetime.utcnow()
        test_coupons = [
            PromoCode(
                code="TEST10",
                discount_percent=10,
                expires_at=now + timedelta(days=7),
                uses_left=5
            ),
            PromoCode(
                code="WELCOME20",
                discount_percent=20,
                expires_at=now + timedelta(days=7),
                uses_left=5
            ),
            PromoCode(
                code="DISCOUNT30",
                discount_percent=30,
                expires_at=now + timedelta(days=7),
                uses_left=5
            ),
        ]
        db.add_all(test_coupons)

    db.commit()
    db.close()
