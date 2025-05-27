from aiogram import Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from db.database import SessionLocal, User
from sqlalchemy.exc import IntegrityError
import re
from bot.keyboards.common import main_menu_keyboard

class Onboarding(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fullname = State()

def register_user_handlers(dp: Dispatcher):

    @dp.message(F.text == "/start")
    async def start(message: Message, state: FSMContext):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        db.close()

        if user and user.full_name and user.phone_number:
            await message.answer("✅ Вы уже зарегистрированы. Вот главное меню:", reply_markup=main_menu_keyboard())
            return

        await message.answer(
            "👋 Добро пожаловать в <b>PhotoExpress</b>!\n\n"
            "📄 Пользовательское соглашение:\n"
            "— Вы соглашаетесь на <b>обработку персональных данных</b>.\n"
            "— Вы соглашаетесь получать <b>уведомления о статусах заказов</b>.\n"
            "— Вы также можете получать <b>рекламные предложения</b> от сервиса.\n\n"
            "Если вы согласны — нажмите кнопку ниже.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="✅ Согласен")]],
                resize_keyboard=True,
                is_persistent=True
            ),
            parse_mode="HTML"
        )

    @dp.message(F.text == "✅ Согласен")
    async def agree_policy(message: Message, state: FSMContext):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                accepted_policy=True
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        db.close()

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)],
                [KeyboardButton(text="✍️ Ввести номер вручную")]
            ],
            resize_keyboard=True,
            is_persistent=True
        )
        await message.answer("Пожалуйста, отправьте ваш номер телефона для связи:", reply_markup=keyboard)
        await state.set_state(Onboarding.waiting_for_phone)

    @dp.message(Onboarding.waiting_for_phone, F.contact)
    async def phone_from_button(message: Message, state: FSMContext):
        phone = message.contact.phone_number
        await save_phone_and_ask_name(message, state, phone)

    @dp.message(Onboarding.waiting_for_phone, F.text)
    async def phone_manual_input(message: Message, state: FSMContext):
        text = message.text.strip()
        if text.lower().startswith("✍️"):
            await message.answer("Введите ваш номер телефона вручную (пример: +79991234567):")
        elif text.startswith("+7") or text.startswith("8"):
            await save_phone_and_ask_name(message, state, text)
        else:
            await message.answer("Пожалуйста, введите корректный номер телефона, начиная с +7")

    async def save_phone_and_ask_name(message: Message, state: FSMContext, phone: str):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        existing_phone_user = db.query(User).filter_by(phone_number=phone).first()

        if existing_phone_user and existing_phone_user.telegram_id != message.from_user.id:
            await message.answer("❗ Пользователь с этим номером уже зарегистрирован. Введите другой номер.")
            db.close()
            return

        if user:
            user.phone_number = phone
            db.commit()
        db.close()

        await message.answer("Теперь укажите ваше <b>ФИО</b> (одной строкой):", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Onboarding.waiting_for_fullname)

    @dp.message(Onboarding.waiting_for_fullname)
    async def fullname_received(message: Message, state: FSMContext):
        full_name = message.text.strip()

        if not re.match(r"^[А-Яа-яA-Za-z]{2,}\s[А-Яа-яA-Za-z]{2,}.*$", full_name):
            await message.answer("❗ Пожалуйста, введите корректное ФИО — минимум имя и фамилия.")
            return

        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        if user:
            user.full_name = full_name
            db.commit()
        db.close()

        await message.answer("✅ Отлично! Регистрация завершена.", reply_markup=main_menu_keyboard())
        await state.clear()
