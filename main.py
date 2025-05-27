import asyncio
import os
import shutil
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from datetime import datetime, timedelta

from db.database import init_db, SessionLocal, Order, User
from bot.handlers.user.onboarding import register_user_handlers
from bot.handlers.user.profile import register_profile_handlers
from bot.handlers.user.upload import register_upload_handlers
from bot.handlers.user.orders import register_orders_handlers
from bot.handlers.user.edit_order import register_edit_order_handlers
from bot.keyboards.common import main_menu_keyboard

load_dotenv()

bot = Bot(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Фоновая задача для удаления неоплаченных заказов
async def unpaid_order_checker(bot: Bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        t1 = now - timedelta(minutes=10)
        t2 = now - timedelta(minutes=20)
        t3 = now - timedelta(minutes=30)

        db = SessionLocal()
        # Фильтр по коду статуса "new"
        orders = db.query(Order).filter(Order.status == "new", Order.paid == False).all()

        for order in orders:
            user = db.query(User).filter_by(id=order.user_id).first()
            if not user:
                continue

            try:
                if order.created_at <= t3:
                    # Удаляем папку с загруженными фотографиями
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
            except Exception as e:
                print(f"[UNPAID_CHECKER ERROR]: {e}")
                continue

        db.commit()
        db.close()

# Основной запуск бота
async def start():
    register_user_handlers(dp)
    register_profile_handlers(dp)
    register_upload_handlers(dp)
    register_orders_handlers(dp)
    register_edit_order_handlers(dp)

    # Запускаем и бота, и фоновую задачу
    await asyncio.gather(
        dp.start_polling(bot),
        unpaid_order_checker(bot)
    )

if __name__ == "__main__":
    init_db()
    asyncio.run(start())