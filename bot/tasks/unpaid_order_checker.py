import asyncio
import os
import shutil
from datetime import datetime, timedelta
from functools import partial

from aiogram import Bot
from sqlalchemy import select, update

from db.async_database import AsyncSessionLocal
from db.database import Order, User


async def _rmtree(path: str) -> None:
    """
    Асинхронно удаляет папку с файлами, не блокируя event-loop.
    """
    if os.path.exists(path):
        # shutil.rmtree выполняем в параллельном потоке
        await asyncio.to_thread(shutil.rmtree, path)


async def unpaid_order_checker(bot: Bot) -> None:
    """
    Каждые 60 секунд обходит заказы со статусом 'new' и paid=False:
      • спустя 10 мин — напоминание, discount → 0.01
      • спустя 20 мин — предупреждение, discount → 0.02
      • спустя 30 мин — удаляет заказ и файлы
    (Пока оставляем старую логику через discount, переезд на reminder_stage сделаем позднее.)
    """
    while True:
        await asyncio.sleep(60)

        now = datetime.utcnow()
        t1 = now - timedelta(minutes=10)
        t2 = now - timedelta(minutes=20)
        t3 = now - timedelta(minutes=30)

        async with AsyncSessionLocal() as session:
            # вытягиваем все NEW-заказы, не оплаченные
            result = await session.execute(
                select(Order).where(
                    Order.status == "new",
                    Order.paid.is_(False)
                )
            )
            orders = result.scalars().all()

            for order in orders:
                # Находим пользователя для уведомления
                user = await session.scalar(
                    select(User).where(User.id == order.user_id)
                )
                if not user:
                    continue  # пропускаем, если нет привязки

                try:
                    # 30 мин — удаляем заказ и папку
                    if order.created_at <= t3:
                        folder = f"uploads/{user.telegram_id}/{order.order_id}"
                        await _rmtree(folder)
                        await session.delete(order)
                        await bot.send_message(
                            user.telegram_id,
                            f"❌ Заказ #{order.order_id[:8]} удалён из-за не оплаты."
                        )

                    # 20 мин — второе предупреждение
                    elif order.created_at <= t2 and float(order.discount) == 0.01:
                        order.discount = 0.02
                        await bot.send_message(
                            user.telegram_id,
                            f"⚠️ Последнее предупреждение: заказ "
                            f"#{order.order_id[:8]} всё ещё не оплачен."
                        )

                    # 10 мин — первое напоминание
                    elif order.created_at <= t1 and float(order.discount) == 0.0:
                        order.discount = 0.01
                        await bot.send_message(
                            user.telegram_id,
                            f"💡 Напоминание: заказ #{order.order_id[:8]} не оплачен."
                        )

                except Exception:
                    # Любая ошибка Telegram API не должна ронять воркер
                    pass

            await session.commit()
