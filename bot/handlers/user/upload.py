import uuid
import shutil
import os
from datetime import datetime

from aiogram import Dispatcher, F
from aiogram.types import (
    Message,
    Document,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import desc
from db.database import SessionLocal, Order, User, OrderStatus, PickupPoint
from bot.services.storage import save_photo_to_order_folder
from bot.services.pricing import calculate_order_price
from bot.services.maps import get_nearest_pickup_points
from bot.keyboards.common import main_menu_keyboard

# Supported print formats
FORMATS = ["10x15", "13x18", "15x21", "21x30 (A4)", "30x40", "30x45"]

class UploadFSM(StatesGroup):
    waiting_for_photo = State()
    waiting_for_format = State()
    waiting_for_copies = State()
    waiting_for_comment = State()
    choosing_pickup_point = State()


def get_status_code(db, label_substring: str) -> str:
    status = (
        db.query(OrderStatus)
        .filter(OrderStatus.label.contains(label_substring))
        .first()
    )
    return status.code if status else "new"


def register_upload_handlers(dp: Dispatcher):
    # 1) Старт загрузки
    @dp.message(F.text == "📂 Загрузить фото")
    async def start_upload(message: Message, state: FSMContext):
        order_id = str(uuid.uuid4())
        await state.update_data(order_id=order_id, photos=[])
        await message.answer(
            "📥 Отправьте фото <b>файлом</b> для сохранения качества.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(UploadFSM.waiting_for_photo)

    # 2) Получение файла
    @dp.message(UploadFSM.waiting_for_photo, F.document)
    async def receive_photo(message: Message, state: FSMContext):
        doc: Document = message.document
        if not doc.mime_type.startswith("image/"):
            await message.answer("❗ Пожалуйста, загрузите изображение файлом.")
            return

        data = await state.get_data()
        file = await message.bot.download(doc)
        filepath = save_photo_to_order_folder(
            message.from_user.id,
            data["order_id"],
            doc.file_name,
            file.read(),
        )
        await state.update_data(
            current_file_path=filepath, current_filename=doc.file_name
        )

        kb_fmt = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=f)] for f in FORMATS],
            resize_keyboard=True,
        )
        await message.answer("Выберите формат печати:", reply_markup=kb_fmt)
        await state.set_state(UploadFSM.waiting_for_format)

    # 3) Получение формата
    @dp.message(UploadFSM.waiting_for_format, F.text.in_(FORMATS))
    async def receive_format(message: Message, state: FSMContext):
        await state.update_data(current_format=message.text)
        await message.answer("Сколько копий напечатать?", reply_markup=ReplyKeyboardRemove())
        await state.set_state(UploadFSM.waiting_for_copies)

    # 4) Получение количества копий
    @dp.message(UploadFSM.waiting_for_copies, F.text)
    async def receive_copies(message: Message, state: FSMContext):
        try:
            cnt = int(message.text.strip())
            assert 1 <= cnt <= 50
        except:
            await message.answer("Введите число копий от 1 до 50.")
            return

        data = await state.get_data()
        photos = data["photos"]
        photos.append({
            "filename": data["current_filename"],
            "path": data["current_file_path"],
            "format": data["current_format"],
            "copies": cnt,
        })
        await state.update_data(photos=photos)

        kb_next = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➕ Добавить ещё фото")],
                [KeyboardButton(text="✅ Завершить и оформить заказ")],
            ],
            resize_keyboard=True,
        )
        await message.answer("✅ Фото добавлено. Что дальше?", reply_markup=kb_next)
        await state.set_state(UploadFSM.waiting_for_photo)

    # 5) Добавить ещё фото
    @dp.message(UploadFSM.waiting_for_photo, F.text == "➕ Добавить ещё фото")
    async def add_more(message: Message, state: FSMContext):
        await message.answer("📥 Отправьте ещё одно фото файлом.")
        await state.set_state(UploadFSM.waiting_for_photo)

    # 6) Завершить и перейти к комментарию
    @dp.message(UploadFSM.waiting_for_photo, F.text == "✅ Завершить и оформить заказ")
    async def finish_upload(message: Message, state: FSMContext):
        kb_cmt = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📝 Без комментариев")]],
            resize_keyboard=True,
        )
        await message.answer(
            "✉ Добавьте комментарий к заказу или нажмите кнопку ниже:",
            reply_markup=kb_cmt,
        )
        await state.set_state(UploadFSM.waiting_for_comment)

    # 7) Получение комментария и сохранение заказа (но БЕЗ финального «📦 Заказ сформирован»)
    @dp.message(UploadFSM.waiting_for_comment, F.text)
    async def receive_comment_and_finalize(message: Message, state: FSMContext):
        data = await state.get_data()
        comment = message.text.strip() if message.text.lower() != "без комментариев" else ""
        photos = data["photos"]
        order_id = data["order_id"]

        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        status_code = get_status_code(db, "Новый")
        _, price, discount = calculate_order_price(photos)

        new_order = Order(
            order_id=order_id,
            user_id=user.id,
            photos=photos,
            comment=comment,
            price=price,
            discount=discount,
            status=status_code,
            paid=False,
            receiver_name=user.full_name,
            receiver_phone=user.phone_number,
            created_at=datetime.utcnow(),
        )
        db.add(new_order)
        db.commit()
        db.close()

        # Здесь НЕ выводим «📦 Заказ сформирован». Сразу переходим к выбору ПВЗ:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(
                    text="📍 Отправить геолокацию(временно не работает)",
                    request_location=True
                )],
                [KeyboardButton(text="📋 Показать список")],
            ],
            resize_keyboard=True,
        )
        await message.answer(
            "✅ Заказ сохранён!\nТеперь выберите пункт выдачи:",
            parse_mode="HTML",
            reply_markup=kb
        )
        await state.set_state(UploadFSM.choosing_pickup_point)

    # 8) Выбор по геолокации
    @dp.message(UploadFSM.choosing_pickup_point, F.content_type == "location")
    async def pickup_by_location(message: Message, state: FSMContext):
        pts = get_nearest_pickup_points(
            message.location.latitude, message.location.longitude
        )
        kb = InlineKeyboardMarkup(row_width=1, inline_keyboard=[])
        for i, p in enumerate(pts, 1):
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"{i}. {p.name} — {p.address}",
                    callback_data=f"select_pp:{p.id}"
                )
            ])
        await message.answer("Найдены ближайшие ПВЗ, выберите:", reply_markup=kb)

    # 9) Выбор из списка
    @dp.message(UploadFSM.choosing_pickup_point, F.text == "📋 Показать список")
    async def pickup_list(message: Message, state: FSMContext):
        pts = get_nearest_pickup_points(55.751244, 37.618423)
        kb = InlineKeyboardMarkup(row_width=1, inline_keyboard=[])
        for i, p in enumerate(pts, 1):
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"{i}. {p.name} — {p.address}",
                    callback_data=f"select_pp:{p.id}"
                )
            ])
        await message.answer("Список ПВЗ:", reply_markup=kb)

    # 10) Обработка выбора ПВЗ → ЗДЕСЬ отправляем полное «📦 Заказ сформирован», включая выбранный ПВЗ
    @dp.callback_query(UploadFSM.choosing_pickup_point, F.data.startswith("select_pp:"))
    async def select_pickup(callback: CallbackQuery, state: FSMContext):
        pp_id = int(callback.data.split(":", 1)[1])
        data = await state.get_data()
        order_id = data.get("order_id")

        db = SessionLocal()
        pp = db.query(PickupPoint).filter_by(id=pp_id).first()
        pp_name, pp_address = pp.name, pp.address

        order = db.query(Order).filter_by(order_id=order_id).first()
        if order:
            order.delivery_point = pp_name
            db.commit()

            # Собираем все данные для финального сообщения:
            photo_lines = [
                f"• {p['filename']} — {p['format']}, {p['copies']} коп." 
                for p in order.photos
            ]
            price_str = f"{float(order.price):.2f}".rstrip("0").rstrip(".")
            discount_str = f"{float(order.discount):.2f}".rstrip("0").rstrip(".")
            comment_display = order.comment or "—"
            delivery_display = pp_name

            text = (
                "📦 <b>Заказ сформирован</b>\n\n"
                + "\n".join(photo_lines) + "\n\n"
                + f"💬 Комментарий: {comment_display}\n"
                + f"💰 Стоимость: <b>{price_str} ₽</b> (скидка: {discount_str} ₽)\n"
                + f"📍 Пункт выдачи: <b>{delivery_display}</b>\n"
                + f"👤 Получатель: {order.receiver_name or '—'}\n"
                + f"📞 Телефон: {order.receiver_phone or '—'}\n\n"
                + "Ваш заказ будет отправлен в обработку после оплаты."
            )

            await callback.message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
        else:
            await callback.message.answer("❗ Не удалось сохранить пункт выдачи.")

        db.close()
        await state.clear()

    # 11) Отмена заказа (во время создания)
    @dp.message(F.text == "❌ Отменить заказ")
    async def cancel_order(message: Message, state: FSMContext):
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        order = (
            db.query(Order)
            .filter_by(user_id=user.id)
            .order_by(desc(Order.created_at))
            .first()
        )
        if order:
            folder = f"uploads/{user.telegram_id}/{order.order_id}"
            if os.path.exists(folder):
                shutil.rmtree(folder)
            db.delete(order)
            db.commit()
            await message.answer("❌ Заказ отменён.", reply_markup=main_menu_keyboard())
        else:
            await message.answer("❗ Нет активного заказа для отмены.")
        db.close()
