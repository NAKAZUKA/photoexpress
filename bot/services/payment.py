from db.database import SessionLocal, Order, OrderStatus, User

async def mark_order_paid(order_id: str) -> Order:
    """
    Помечает заказ как оплаченный (paid=True), оставляет статус 'new'.
    Возвращает обновленный объект Order.
    """
    db = SessionLocal()
    order = db.query(Order).filter_by(order_id=order_id).first()
    if not order:
        db.close()
        return None

    # Помечаем как оплаченный
    order.paid = True
    db.commit()

    db.refresh(order)
    db.close()
    return order