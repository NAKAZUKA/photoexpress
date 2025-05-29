import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from db.database import SessionLocal, Order, OrderStatus, User

async def order_status_updater(bot: Bot):
    """
    Каждые 60 секунд переводит оплаченные заказы со статусом 'new' старше 5 минут в 'in_progress'
    и уведомляет пользователя.
    """
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        threshold = now - timedelta(minutes=5)

        db = SessionLocal()
        # находим все оплаченные новые заказы, старше threshold
        ready = (
            db.query(Order)
            .filter(Order.status == "new", Order.paid == True, Order.created_at <= threshold)
            .all()
        )
        in_prog = db.query(OrderStatus).filter_by(code="in_progress").first()

        for order in ready:
            order.status = in_prog.code
            db.commit()

            user = db.query(User).filter_by(id=order.user_id).first()
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"🛠 Заказ #{order.order_id[:8]} переведён в статус «{in_prog.label}»."
                )
            except Exception:
                pass

        db.close()
