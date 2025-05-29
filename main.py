import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from db.database import init_db
from bot.handlers.user.onboarding import register_user_handlers
from bot.handlers.user.profile import register_profile_handlers
from bot.handlers.user.upload import register_upload_handlers
from bot.handlers.user.orders import register_orders_handlers
from bot.handlers.user.edit_order import register_edit_order_handlers
from bot.handlers.user.payment_handlers import register_payment_handlers
from bot.tasks.unpaid_order_checker import unpaid_order_checker
from bot.tasks.order_status_updater import order_status_updater

load_dotenv()

bot = Bot(
    token=os.getenv("TELEGRAM_BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

async def start():
    init_db()

    # регистрируем хендлеры
    register_user_handlers(dp)
    register_profile_handlers(dp)
    register_upload_handlers(dp)
    register_orders_handlers(dp)
    register_edit_order_handlers(dp)
    register_payment_handlers(dp)

    # запускаем polling и оба фоновых воркера
    await asyncio.gather(
        dp.start_polling(bot),
        unpaid_order_checker(bot),
        order_status_updater(bot),
    )

if __name__ == "__main__":
    asyncio.run(start())
