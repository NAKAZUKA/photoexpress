from aiogram import Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from db.database import SessionLocal, User
from bot.keyboards.common import main_menu_keyboard

class ProfileEdit(StatesGroup):
    waiting_for_new_fullname = State()
    waiting_for_new_phone = State()

def register_profile_handlers(dp: Dispatcher):

    @dp.message(F.text == "👤 Профиль")
    async def profile_main(message: Message, state: FSMContext):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        db.close()

        if not user:
            await message.answer("🙁 Вы ещё не зарегистрированы. Введите /start")
            return

        text = (
            f"<b>Ваш профиль:</b>\n"
            f"👤 ФИО: {user.full_name or 'не указано'}\n"
            f"📱 Телефон: {user.phone_number or 'не указано'}\n\n"
            "Вы можете изменить данные:"
        )

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✏ Изменить ФИО")],
                [KeyboardButton(text="✏ Изменить номер телефона")],
                [KeyboardButton(text="🗑 Удалить аккаунт")],
                [KeyboardButton(text="🔙 Назад в меню")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )

        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    @dp.message(F.text == "✏ Изменить ФИО")
    async def change_fullname(message: Message, state: FSMContext):
        await message.answer("Введите новое <b>ФИО</b>:", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        await state.set_state(ProfileEdit.waiting_for_new_fullname)

    @dp.message(ProfileEdit.waiting_for_new_fullname)
    async def save_fullname(message: Message, state: FSMContext):
        full_name = message.text.strip()
        if len(full_name.split()) < 2 or any(len(w) < 2 for w in full_name.split()):
            await message.answer("❗ Пожалуйста, введите корректное ФИО.")
            return

        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        if user:
            user.full_name = full_name
            db.commit()
        db.close()
        await message.answer("✅ ФИО обновлено.", reply_markup=main_menu_keyboard())
        await state.clear()

    @dp.message(F.text == "✏ Изменить номер телефона")
    async def change_phone(message: Message, state: FSMContext):
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)],
                [KeyboardButton(text="✍️ Ввести вручную")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Отправьте новый номер телефона:", reply_markup=kb)
        await state.set_state(ProfileEdit.waiting_for_new_phone)

    @dp.message(ProfileEdit.waiting_for_new_phone, F.contact)
    async def phone_from_contact(message: Message, state: FSMContext):
        await save_phone(message, state, message.contact.phone_number)

    @dp.message(ProfileEdit.waiting_for_new_phone, F.text)
    async def phone_from_text(message: Message, state: FSMContext):
        text = message.text.strip()
        if text.startswith("+7") or text.startswith("8"):
            await save_phone(message, state, text)
        else:
            await message.answer("Введите корректный номер телефона, начиная с +7")

    async def save_phone(message: Message, state: FSMContext, phone: str):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        if user:
            user.phone_number = phone
            db.commit()
        db.close()
        await message.answer("✅ Номер телефона обновлён.", reply_markup=main_menu_keyboard())
        await state.clear()

    @dp.message(F.text == "🗑 Удалить аккаунт")
    async def delete_account(message: Message, state: FSMContext):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        if user:
            db.delete(user)
            db.commit()
            await message.answer("❌ Ваш аккаунт удалён. Для повторной регистрации используйте /start", reply_markup=ReplyKeyboardRemove())
        else:
            await message.answer("Аккаунт не найден.")
        db.close()
        await state.clear()

    @dp.message(F.text == "🔙 Назад в меню")
    async def back_to_menu(message: Message, state: FSMContext):
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
