# bot/services/pricing.py

from .promo import apply_first_order_discount, validate_and_apply_promocode, PromoError

# Новые (обновлённые) цены для форматов
PRICES = {
    "10x15": 20,
    "13x18": 30,
    "15x21": 40,
    "21x30 (A4)": 50,
    "30x40": 60,
    "30x45": 70,
}

DISCOUNT_THRESHOLDS = {
    50: 0.95,   # 5% скидка, если суммарное количество копий ≥50
    100: 0.90,  # 10% скидка, если ≥100
}

def calculate_order_price(
    photos: list[dict],
    user_id: int | None = None,
    promocode: str | None = None
) -> tuple[float, float, float]:
    """
    Возвращает (raw_total, final_total, discount_amount).
    - raw_total — сумма без учёта скидок;
    - final_total — итоговая сумма после всех скидок;
    - discount_amount — сколько в рублях сэкономлено.

    Логика:
    1) Считаем raw_total по перечисленным форматам и копиям.
    2) Сначала пробуем (если user_id передан) дать 30% на первый заказ: 
       apply_first_order_discount(user_id, raw_total).
    3) Если передан promocode и это не первый заказ, применяем промокод: 
       validate_and_apply_promocode(promocode, raw_total).
    4) Если ни первого заказа, ни промокода нет — возвращаем raw_total и нулевую скидку.
    """
    raw_total = 0.0
    total_copies = 0

    for p in photos:
        fmt = p.get("format", "10x15")
        copies = p.get("copies", 1)
        unit_price = PRICES.get(fmt, 20)
        raw_total += unit_price * copies
        total_copies += copies

    # Ещё раз: базовая скидка по объёму копий (threshold), потом — 
    # скидка на первый заказ или промокод (они перекрывают).
    # Но исходный код до этого уже выдавал скидки по порогу DISCOUNT_THRESHOLDS.
    discount_multiplier = 1.0
    for threshold, mult in sorted(DISCOUNT_THRESHOLDS.items()):
        if total_copies >= threshold:
            discount_multiplier = mult

    discounted_by_threshold = round(raw_total * discount_multiplier, 2)
    threshold_discount_amount = round(raw_total - discounted_by_threshold, 2)

    # Теперь перекрываем этим (для простоты): 
    # если задан user_id и first_order — 30%. Иначе если передан promocode — применяем его.
    final_total = discounted_by_threshold
    total_discount = threshold_discount_amount

    if user_id is not None:
        # Проверяем, первый ли заказ
        new_total_first, first_discount = apply_first_order_discount(user_id, discounted_by_threshold)
        if first_discount > 0:
            final_total = new_total_first
            total_discount = round(threshold_discount_amount + first_discount, 2)
            return raw_total, final_total, total_discount

    if promocode:
        try:
            promo_total, promo_discount = validate_and_apply_promocode(promocode, discounted_by_threshold)
        except PromoError:
            # Если промокод неверный, возвращаем ошибку наверх
            raise
        final_total = promo_total
        total_discount = round(threshold_discount_amount + promo_discount, 2)
        return raw_total, final_total, total_discount

    # Если ни первого заказа, ни промокода нет — возвращаем скидку по объёму (threshold)
    return raw_total, discounted_by_threshold, threshold_discount_amount
