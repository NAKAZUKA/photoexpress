PRICES = {
    "10x15": 10,
    "15x21": 18,
    "A4": 25,
}

DISCOUNT_THRESHOLDS = {
    50: 0.95,   # 5% скидка
    100: 0.90,  # 10% скидка
}

def calculate_order_price(photos: list[dict]) -> tuple[float, float, float]:
    total = 0
    count = 0

    for photo in photos:
        fmt = photo.get("format", "10x15")
        copies = photo.get("copies", 1)
        price_per_unit = PRICES.get(fmt, 10)
        total += price_per_unit * copies
        count += copies

    discount_multiplier = 1.0
    for threshold, multiplier in sorted(DISCOUNT_THRESHOLDS.items()):
        if count >= threshold:
            discount_multiplier = multiplier

    discounted_total = round(total * discount_multiplier, 2)
    discount_value = round(total - discounted_total, 2)

    return total, discounted_total, discount_value
