from datetime import datetime
from db.database import SessionLocal, PromoCode, User

class PromoError(Exception):
    """Ошибка применения промокода или первой скидки."""
    pass

def apply_first_order_discount(user_id: int, current_total: float) -> tuple[float, float]:
    """
    Если пользователь ещё не оплачивал ни одного заказа — даёт 30% скидку.
    Возвращает (new_total, discount_amount).
    """
    db = SessionLocal()
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        db.close()
        raise PromoError("Пользователь не найден")

    # Находим, был ли у него ранее оплаченный заказ
    if not getattr(user, "first_order_paid", False):
        discount_amount = round(current_total * 0.30, 2)
        new_total = round(current_total - discount_amount, 2)
    else:
        discount_amount = 0.0
        new_total = current_total

    db.close()
    return new_total, discount_amount

def validate_and_apply_promocode(code: str, base_total: float) -> tuple[float, float]:
    """
    Проверяет, что промокод существует, не истёк и не исчерпан.
    Применяет, уменьшает uses_left и возвращает (new_total, discount_amount).
    """
    db = SessionLocal()
    promo = db.query(PromoCode).filter_by(code=code).first()
    if not promo:
        db.close()
        raise PromoError("Промокод не найден")

    if promo.expires_at < datetime.utcnow():
        db.close()
        raise PromoError("Срок действия промокода истёк")

    if promo.uses_left is not None and promo.uses_left <= 0:
        db.close()
        raise PromoError("Промокод исчерпан")

    # Считаем скидку
    discount_amount = round(base_total * (promo.discount_percent / 100), 2)
    new_total = round(base_total - discount_amount, 2)

    # Уменьшаем количество использований
    if promo.uses_left is not None:
        promo.uses_left -= 1
        db.commit()

    db.close()
    return new_total, discount_amount
