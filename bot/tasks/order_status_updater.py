import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select

# модели остаются теми же — мы лишь меняем способ доступа к БД
from db.database import Order, OrderStatus, User
from db.async_database import AsyncSessionLocal


async def order_status_updater(bot: Bot) -> None:
    """
    Каждые 60 секунд:
    • Находит оплаченные заказы со статусом 'new', созданные ≥ 5 минут назад
    • Переводит их в 'in_progress'
    • Шлёт пользователю уведомление
    Работает полностью асинхронно, не блокируя event-loop.
    """
    while True:
        await asyncio.sleep(60)

        now = datetime.utcnow()
        threshold = now - timedelta(minutes=5)

        async with AsyncSessionLocal() as session:
            # 1) выбираем заказы, которые пора перевести
            result = await session.execute(
                select(Order).where(
                    Order.status == "new",
                    Order.paid.is_(True),
                    Order.created_at <= threshold
                )
            )
            orders_to_process = result.scalars().all()

            if not orders_to_process:
                continue  # ничего не делаем — ждём следующего цикла

            # 2) получаем объект статуса "in_progress" один раз
            in_prog: OrderStatus | None = await session.scalar(
                select(OrderStatus).where(OrderStatus.code == "in_progress")
            )
            if in_prog is None:  # защита от случаев, когда в БД нет такого статуса
                in_prog_code, in_prog_label = "in_progress", "🛠 В обработке"
            else:
                in_prog_code, in_prog_label = in_prog.code, in_prog.label

            # 3) обновляем каждый заказ и шлём сообщение
            for order in orders_to_process:
                order.status = in_prog_code

                # берём пользователя (можем «прижать» selectinload, но здесь достаточно scalar)
                user = await session.scalar(
                    select(User).where(User.id == order.user_id)
                )
                if user:
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            f"🛠 Заказ #{order.order_id[:8]} переведён в статус «{in_prog_label}»."
                        )
                    except Exception:
                        # не прерываем цикл, если Telegram API дал ошибку
                        pass

            # 4) фиксируем изменения
            await session.commit()
