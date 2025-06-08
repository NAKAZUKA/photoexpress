# bot/handlers/user/upload.py

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
from bot.services.pricing import calculate_order_price, PromoError
from bot.services.maps import get_nearest_pickup_points
from bot.keyboards.common import main_menu_keyboard

# Supported print formats
FORMATS = ["10x15", "13x18", "15x21", "21x30 (A4)", "30x40", "30x45"]


class UploadFSM(StatesGroup):
    waiting_for_photo        = State()
    waiting_for_format       = State()
    waiting_for_copies       = State()
    waiting_for_comment      = State()
    waiting_for_promocode    = State()    # НОВЫЙ СТАТУС для ввода промокода
    choosing_pickup_point    = State()


def get_status_code(db, label_substring: str) -> str:
    status = (
        db.query(OrderStatus)
          .filter(OrderStatus.label.contains(label_substring))
          .first()
    )
    return status.code if status else "new"


def register_upload_handlers(dp: Dispatcher):
    # 1) Старт: “📂 Загрузить фото”
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

    # 2) Если пришёл документ (файл)
    @dp.message(UploadFSM.waiting_for_photo, F.document)
    async def receive_photo(message: Message, state: FSMContext):
        doc: Document = message.document
        if not doc.mime_type.startswith("image/"):
            await message.answer(
                "❗ Пожалуйста, загрузите изображение именно <b>файлом</b>.",
                parse_mode="HTML"
            )
            return

        data = await state.get_data()
        file_bytes = await message.bot.download(doc)
        filepath = save_photo_to_order_folder(
            message.from_user.id,
            data["order_id"],
            doc.file_name,
            file_bytes.read(),
        )
        await state.update_data(
            current_file_path=filepath,
            current_filename=doc.file_name
        )

        kb_fmt = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=f)] for f in FORMATS],
            resize_keyboard=True
        )
        await message.answer("Выберите формат печати:", reply_markup=kb_fmt)
        await state.set_state(UploadFSM.waiting_for_format)

    # 2.1) Если пришло НЕ document и при этом текст не равен кнопкам «➕ Добавить ещё фото» или «✅ Завершить и оформить заказ»,
    #      тогда просим прислать файл
    @dp.message(
        UploadFSM.waiting_for_photo,
        F.content_type != "document",
        ~F.text.in_(["➕ Добавить ещё фото", "✅ Завершить и оформить заказ"])
    )
    async def ask_photo_as_file(message: Message, state: FSMContext):
        await message.answer(
            "❗ Пожалуйста, отправьте фото <b>файлом</b>, чтобы сохранить качество.",
            parse_mode="HTML"
        )
        # остаёмся в состоянии waiting_for_photo

    # 3) Получаем формат
    @dp.message(UploadFSM.waiting_for_format, F.text.in_(FORMATS))
    async def receive_format(message: Message, state: FSMContext):
        await state.update_data(current_format=message.text)
        await message.answer("Сколько копий напечатать?", reply_markup=ReplyKeyboardRemove())
        await state.set_state(UploadFSM.waiting_for_copies)

    # 3.1) Если в waiting_for_format пришёл текст, которого нет в FORMATS
    @dp.message(UploadFSM.waiting_for_format)
    async def ask_valid_format(message: Message, state: FSMContext):
        await message.answer("❗ Пожалуйста, выберите формат из предложенных вариантов.")

    # 4) Получаем количество копий
    @dp.message(UploadFSM.waiting_for_copies, F.text)
    async def receive_copies(message: Message, state: FSMContext):
        try:
            cnt = int(message.text.strip())
            assert 1 <= cnt <= 50
        except:
            await message.answer("❗ Введите число копий от 1 до 50.")
            return

        data = await state.get_data()
        photos = data.get("photos", [])
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
            resize_keyboard=True
        )
        await message.answer("✅ Фото добавлено. Что дальше?", reply_markup=kb_next)
        await state.set_state(UploadFSM.waiting_for_photo)

    # 4.1) Если вместо числа пришёл другой текст в waiting_for_copies
    @dp.message(UploadFSM.waiting_for_copies)
    async def ask_valid_copies(message: Message, state: FSMContext):
        await message.answer("❗ Введите корректное число копий (от 1 до 50).")

    # 5) “➕ Добавить ещё фото”
    @dp.message(UploadFSM.waiting_for_photo, F.text == "➕ Добавить ещё фото")
    async def add_more(message: Message, state: FSMContext):
        await message.answer(
            "📥 Отправьте ещё одно фото <b>файлом</b> для сохранения качества.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(UploadFSM.waiting_for_photo)

    # 6) “✅ Завершить и оформить заказ” → спрашиваем комментарий
    @dp.message(UploadFSM.waiting_for_photo, F.text == "✅ Завершить и оформить заказ")
    async def finish_upload(message: Message, state: FSMContext):
        kb_cmt = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📝 Без комментариев")]],
            resize_keyboard=True
        )
        await message.answer(
            "✉ Добавьте комментарий к заказу или нажмите кнопку ниже:",
            reply_markup=kb_cmt
        )
        await state.set_state(UploadFSM.waiting_for_comment)

    # 7) Получаем комментарий и решаем, первый ли заказ
    @dp.message(UploadFSM.waiting_for_comment, F.text)
    async def receive_comment_and_finalize(message: Message, state: FSMContext):
        data = await state.get_data()
        comment = message.text.strip() if message.text.lower() != "без комментариев" else ""
        photos = data.get("photos", [])
        order_id = data.get("order_id")

        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        if not user:
            db.close()
            await message.answer("❗ Пользователь не найден в БД.")
            await state.clear()
            return

        # 1) Считаем базовую сумму (raw_total), учитываем threshold-скидку (по DISCOUNT_THRESHOLDS)
        raw, after_threshold, thresh_disc = calculate_order_price(photos)

        # 2) Если первый заказ (first_order_paid == False) — сразу даём 30%:
        if not user.first_order_paid:
            first_discount_amount = round(after_threshold * 0.30, 2)
            final_price = round(after_threshold - first_discount_amount, 2)
            total_discount = round(thresh_disc + first_discount_amount, 2)

            # Сохраняем заказ и сразу флагируем у пользователя, что первый заказ сделан
            status_code = get_status_code(db, "Новый")
            new_order = Order(
                order_id=order_id,
                user_id=user.id,
                photos=photos,
                comment=comment,
                price=final_price,
                discount=total_discount,
                status=status_code,
                paid=False,
                receiver_name=user.full_name,
                receiver_phone=user.phone_number,
                created_at=datetime.utcnow(),
            )
            db.add(new_order)

            # Помечаем, что у пользователя первый заказ уже “занят”
            user.first_order_paid = True
            db.commit()
            db.close()

            # Говорим о стоимости и предлагаем выбрать ПВЗ:
            kb_pickup = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(
                        text="📍 Отправить геолокацию (временно не работает)",
                        request_location=True
                    )],
                    [KeyboardButton(text="📋 Показать список")],
                ],
                resize_keyboard=True
            )
            await message.answer(
                f"✅ Заказ сохранён!\n\n"
                f"💰 Итоговая стоимость: <b>{final_price:.2f} ₽</b> (скидка: {total_discount:.2f} ₽)\n\n"
                "Теперь выберите пункт выдачи:",
                parse_mode="HTML",
                reply_markup=kb_pickup
            )
            await state.set_state(UploadFSM.choosing_pickup_point)
            return

        # 3) Если НЕ первый заказ → спрашиваем промокод, показываем кнопку «Пропустить»
        db.close()
        await state.update_data(
            raw_price=after_threshold,
            threshold_discount=thresh_disc,
            comment=comment,
            photos=photos  # сохраняем список фото, чтобы не потерять
        )

        kb_skip = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Пропустить")]],
            resize_keyboard=True
        )
        await message.answer(
            "Введите промокод для скидки или нажмите кнопку «Пропустить», чтобы продолжить без кода:",
            reply_markup=kb_skip
        )
        await state.set_state(UploadFSM.waiting_for_promocode)

    # 8) Обработка ввода промокода (уже НЕ первый заказ)
    @dp.message(UploadFSM.waiting_for_promocode, F.text)
    async def apply_promocode(message: Message, state: FSMContext):
        data = await state.get_data()
        raw_after_threshold = data.get("raw_price", 0.0)
        threshold_discount = data.get("threshold_discount", 0.0)
        comment = data.get("comment", "")
        order_id = data.get("order_id")
        photos = data.get("photos", [])

        promo_code_text = message.text.strip().lower()
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=message.from_user.id).first()
        status_code = get_status_code(db, "Новый")

        # Если пользователь нажал «Пропустить» или ввёл «без промокода»
        if promo_code_text in ("пропустить", "без промокода", "нет", "skip"):
            final_price = raw_after_threshold
            total_discount = threshold_discount

        else:
            # Пробуем применить промокод:
            from bot.services.promo import validate_and_apply_promocode
            try:
                promo_total, promo_disc = validate_and_apply_promocode(promo_code_text, raw_after_threshold)
                final_price = promo_total
                total_discount = round(threshold_discount + promo_disc, 2)
            except PromoError as e:
                # Некорректный/истёкший/исчерпанный промокод — предлагаем попробовать ещё раз или пропустить
                await message.answer(
                    f"❗ Ошибка с промокодом: {str(e)}\n"
                    "Попробуйте ещё раз или нажмите «Пропустить».",
                    parse_mode="HTML"
                )
                db.close()
                return

            # Если промокод применён, сообщаем об этом
            await message.answer(
                f"✅ Промокод <b>{promo_code_text}</b> применён. "
                f"Дополнительная скидка: {promo_disc:.2f} ₽.",
                parse_mode="HTML"
            )

        # Сохраняем заказ (со всеми скидками):
        new_order = Order(
            order_id=order_id,
            user_id=user.id,
            photos=photos,
            comment=comment,
            price=final_price,
            discount=total_discount,
            status=status_code,
            paid=False,
            receiver_name=user.full_name,
            receiver_phone=user.phone_number,
            created_at=datetime.utcnow(),
        )
        db.add(new_order)
        db.commit()
        db.close()

        # Предлагаем выбрать ПВЗ:
        kb_pickup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(
                    text="📍 Отправить геолокацию (временно не работает)",
                    request_location=True
                )],
                [KeyboardButton(text="📋 Показать список")],
            ],
            resize_keyboard=True
        )
        await message.answer(
            f"✅ Заказ сохранён!\n\n"
            f"💰 Итоговая стоимость: <b>{final_price:.2f} ₽</b> (скидка: {total_discount:.2f} ₽)\n\n"
            "Теперь выберите пункт выдачи:",
            parse_mode="HTML",
            reply_markup=kb_pickup
        )
        await state.set_state(UploadFSM.choosing_pickup_point)

    # 9) Выбор ПВЗ по локации
    @dp.message(UploadFSM.choosing_pickup_point, F.content_type == "location")
    async def pickup_by_location(message: Message, state: FSMContext):
        pts = get_nearest_pickup_points(
            message.location.latitude, message.location.longitude
        )
        kb = InlineKeyboardMarkup(row_width=1, inline_keyboard=[])
        for idx, p in enumerate(pts, 1):
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"{idx}. {p.name} — {p.address}",
                    callback_data=f"select_pp:{p.id}"
                )
            ])
        await message.answer("Найдены ближайшие ПВЗ, выберите:", reply_markup=kb)

    # 10) Выбор ПВЗ из списка
    @dp.message(UploadFSM.choosing_pickup_point, F.text == "📋 Показать список")
    async def pickup_list(message: Message, state: FSMContext):
        pts = get_nearest_pickup_points(55.751244, 37.618423)
        kb = InlineKeyboardMarkup(row_width=1, inline_keyboard=[])
        for idx, p in enumerate(pts, 1):
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"{idx}. {p.name} — {p.address}",
                    callback_data=f"select_pp:{p.id}"
                )
            ])
        await message.answer("Список ПВЗ:", reply_markup=kb)

    # 11) Обработка выбора ПВЗ и финальное сообщение
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

            photo_lines = [
                f"• {p['filename']} — {p['format']}, {p['copies']} коп."
                for p in order.photos
            ]
            price_str    = f"{float(order.price):.2f}".rstrip("0").rstrip(".")
            discount_str = f"{float(order.discount):.2f}".rstrip("0").rstrip(".")
            comment_disp = order.comment or "—"
            delivery_disp= pp_name

            final_text = (
                "📦 <b>Заказ сформирован</b>\n\n"
                + "\n".join(photo_lines) + "\n\n"
                + f"💬 Комментарий: {comment_disp}\n"
                + f"💰 Стоимость: <b>{price_str} ₽</b> (скидка: {discount_str} ₽)\n"
                + f"📍 Пункт выдачи: <b>{delivery_disp}</b>\n"
                + f"👤 Получатель: {order.receiver_name or '—'}\n"
                + f"📞 Телефон: {order.receiver_phone or '—'}\n\n"
                + "Ваш заказ будет отправлен в обработку после оплаты."
            )
            await callback.message.answer(final_text, parse_mode="HTML", reply_markup=main_menu_keyboard())
        else:
            await callback.message.answer("❗ Не удалось сохранить пункт выдачи.")
        db.close()
        await state.clear()

    # 12) Отмена заказа (во время создания)
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
