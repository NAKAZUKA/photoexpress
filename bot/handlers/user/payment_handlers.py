from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from db.database import SessionLocal, OrderStatus, User
from bot.services.payment import mark_order_paid
from .orders import _send_orders_list  # чтобы обновить карточку после оплаты

class PaymentHandlers:
    @staticmethod
    def register(dp: Dispatcher):
        @dp.callback_query(F.data.startswith("pay:"))
        async def pay_order_callback(callback: CallbackQuery, state: FSMContext):
            order_id = callback.data.split(":", 1)[1]
            # Обновляем в БД
            updated_order = await mark_order_paid(order_id)
            if not updated_order:
                await callback.answer("❗ Заказ не найден.", show_alert=True)
                return

            # Берем текущую категорию и страницу из state
            data = await state.get_data()
            status_code = data.get("status_filter")
            page = data.get("page", 0)

            # Перезагружаем список заказов
            db = SessionLocal()
            user = db.query(User).filter_by(telegram_id=callback.from_user.id).first()
            status = db.query(OrderStatus).filter_by(code=status_code).first()
            orders = (
                db.query(updated_order.__class__)
                  .filter_by(user_id=user.id, status=status_code)
                  .order_by(updated_order.__class__.created_at.desc())
                  .offset(page * 3)
                  .limit(3)
                  .all()
            )
            db.close()

            # Обновляем карточку списка
            await _send_orders_list(callback.message, orders, status.label, page)
            await callback.answer("✅ Оплата проведена", show_alert=False)

# регистрация

def register_payment_handlers(dp: Dispatcher):
    PaymentHandlers.register(dp)
