# bot/services/promo.py

from datetime import datetime
from db.database import SessionLocal, PromoCode, User

class PromoError(Exception):
    pass


def apply_first_order_discount(user_id: int, base_total: float) -> tuple[float, float]:
    """
    Если это первый оплаченный заказ пользователя, даём 30% скидку.
    Возвращает (new_total, discount_amount).
    """
    db = SessionLocal()
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        db.close()
        raise PromoError("Пользователь не найден в БД")

    if not user.first_order_paid:
        # Применяем 30% скидку
        discount_amount = round(base_total * 0.30, 2)
        new_total = round(base_total - discount_amount, 2)
    else:
        discount_amount = 0.0
        new_total = base_total

    db.close()
    return new_total, discount_amount


def validate_and_apply_promocode(code: str, base_total: float) -> tuple[float, float]:
    """
    Проверяет промокод, применяет процент. 
    Возвращает (new_total, discount_amount).
    Может бросить PromoError с текстом ошибки.
    """
    db = SessionLocal()
    promo = db.query(PromoCode).filter_by(code=code).first()
    if not promo:
        db.close()
        raise PromoError("Промокод не найден")

    if promo.expires_at < datetime.utcnow():
        db.close()
        raise PromoError("Промокод истёк")

    if promo.uses_left is not None and promo.uses_left <= 0:
        db.close()
        raise PromoError("Промокод исчерпан")

    discount_amount = round(base_total * promo.discount_percent / 100, 2)
    new_total = round(base_total - discount_amount, 2)

    # Уменьшаем счётчик uses_left, если он задан
    if promo.uses_left is not None:
        promo.uses_left -= 1

    db.commit()
    db.close()
    return new_total, discount_amount
