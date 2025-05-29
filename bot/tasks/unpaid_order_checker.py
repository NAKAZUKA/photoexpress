import asyncio
import os
import shutil
from datetime import datetime, timedelta

from aiogram import Bot
from db.database import SessionLocal, Order, User

async def unpaid_order_checker(bot: Bot):
    """
    Каждые 60 секунд проверяет заказы со статусом 'new' и paid=False.
    - Через 10 минут (discount==0.0) шлёт напоминание и ставит discount=0.01
    - Через 20 минут (discount==0.01) шлёт предупреждение и ставит discount=0.02
    - Через 30 минут удаляет заказ и папку с файлами.
    """
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        t1 = now - timedelta(minutes=10)
        t2 = now - timedelta(minutes=20)
        t3 = now - timedelta(minutes=30)

        db = SessionLocal()
        orders = db.query(Order).filter(Order.status == "new", Order.paid == False).all()

        for order in orders:
            user = db.query(User).filter_by(id=order.user_id).first()
            try:
                if order.created_at <= t3:
                    # удаляем сам заказ и файлы
                    folder = f"uploads/{user.telegram_id}/{order.order_id}"
                    if os.path.exists(folder):
                        shutil.rmtree(folder)
                    db.delete(order)
                    await bot.send_message(
                        user.telegram_id,
                        f"❌ Заказ #{order.order_id[:8]} удалён из-за не оплаты."
                    )
                elif order.created_at <= t2 and float(order.discount) == 0.01:
                    await bot.send_message(
                        user.telegram_id,
                        f"⚠️ Последнее предупреждение: заказ #{order.order_id[:8]} не оплачен."
                    )
                    order.discount = 0.02
                elif order.created_at <= t1 and float(order.discount) == 0.0:
                    await bot.send_message(
                        user.telegram_id,
                        f"💡 Напоминание: заказ #{order.order_id[:8]} всё ещё не оплачен."
                    )
                    order.discount = 0.01
            except Exception:
                pass

        db.commit()
        db.close()
