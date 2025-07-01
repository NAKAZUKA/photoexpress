# bot/services/payment.py
from db.database import SessionLocal, Order, User

async def mark_order_paid(order_id: str) -> Order | None:
    """
    Помечает заказ как оплаченный и, если это первый оплаченный заказ
    пользователя, выставляет user.first_order_paid = True.
    """
    db = SessionLocal()
    order = db.query(Order).filter_by(order_id=order_id).first()
    if not order:
        db.close()
        return None

    order.paid = True

    user = db.query(User).filter_by(id=order.user_id).first()
    if user and not user.first_order_paid:
        user.first_order_paid = True

    db.commit()          
    db.refresh(order)    
    db.close()
    return order
