from aiogram import Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import SessionLocal, User, Order
from bot.keyboards.common import main_menu_keyboard

class EditOrderFSM(StatesGroup):
    choosing_field = State()
    editing_fullname = State()
    editing_phone = State()
    editing_comment = State()

def register_edit_order_handlers(dp: Dispatcher):

    @dp.message(F.text == "✏ Изменить заказ")
    async def start_edit_order(message: Message, state: FSMContext):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        last_order = db.query(Order).filter_by(user_id=user.id).order_by(Order.created_at.desc()).first()
        db.close()

        if not last_order or last_order.status != "new":
            await message.answer("Вы можете редактировать только активный (новый) заказ.")
            return

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="👤 Изменить ФИО")],
                [KeyboardButton(text="📞 Изменить номер телефона")],
                [KeyboardButton(text="✉ Изменить комментарий")],
                [KeyboardButton(text="🔙 Назад к заказу")]
            ],
            resize_keyboard=True
        )

        await message.answer("Что вы хотите изменить?", reply_markup=kb)
        await state.set_state(EditOrderFSM.choosing_field)

    @dp.message(EditOrderFSM.choosing_field, F.text == "👤 Изменить ФИО")
    async def edit_fullname(message: Message, state: FSMContext):
        await message.answer("Введите новое ФИО:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(EditOrderFSM.editing_fullname)

    @dp.message(EditOrderFSM.editing_fullname)
    async def save_fullname(message: Message, state: FSMContext):
        full_name = message.text.strip()
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        user.full_name = full_name
        db.commit()
        db.close()
        await message.answer("✅ ФИО обновлено.", reply_markup=main_menu_keyboard())
        await state.clear()

    @dp.message(EditOrderFSM.choosing_field, F.text == "📞 Изменить номер телефона")
    async def edit_phone(message: Message, state: FSMContext):
        await message.answer("Введите новый номер телефона:")
        await state.set_state(EditOrderFSM.editing_phone)

    @dp.message(EditOrderFSM.editing_phone)
    async def save_phone(message: Message, state: FSMContext):
        phone = message.text.strip()
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        user.phone_number = phone
        db.commit()
        db.close()
        await message.answer("✅ Номер телефона обновлён.", reply_markup=main_menu_keyboard())
        await state.clear()

    @dp.message(EditOrderFSM.choosing_field, F.text == "✉ Изменить комментарий")
    async def edit_comment(message: Message, state: FSMContext):
        await message.answer("Введите новый комментарий к заказу:")
        await state.set_state(EditOrderFSM.editing_comment)

    @dp.message(EditOrderFSM.editing_comment)
    async def save_comment(message: Message, state: FSMContext):
        new_comment = message.text.strip()
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        order = db.query(Order).filter_by(user_id=user.id).order_by(Order.created_at.desc()).first()
        if order and order.status == "new":
            order.comment = new_comment
            db.commit()
            await message.answer("✅ Комментарий обновлён.", reply_markup=main_menu_keyboard())
        else:
            await message.answer("Невозможно обновить комментарий: нет активного заказа.")
        db.close()
        await state.clear()

    @dp.message(EditOrderFSM.choosing_field, F.text == "🔙 Назад к заказу")
    async def back_to_order(message: Message, state: FSMContext):
        await message.answer("Возвращаемся к заказу.", reply_markup=main_menu_keyboard())
        await state.clear()
