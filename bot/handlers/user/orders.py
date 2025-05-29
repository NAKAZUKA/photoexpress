import os
import shutil
from aiogram import Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import desc
from sqlalchemy.orm.attributes import flag_modified
from db.database import SessionLocal, Order, User, OrderStatus, PickupPoint

FORMATS = ["10x15", "13x18", "15x21", "21x30 (A4)", "30x40", "30x45"]

class OrdersFSM(StatesGroup):
    choosing_status = State()
    browsing_orders = State()
    editing_order_id = State()
    editing_field_choice = State()
    editing_value_input = State()
    confirming_cancel = State()
    editing_pickup = State()

def get_status_code(db, label_substring: str) -> str:
    status = db.query(OrderStatus).filter(OrderStatus.label.contains(label_substring)).first()
    return status.code if status else "new"

async def _send_orders_list(message: Message, orders: list[Order], status_label: str, page: int):
    text = f"<b>📦 Заказы — {status_label}</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for o in orders:
        photo_lines = [
            f"• {p['filename']} — {p['format']}, {p['copies']} коп."
            for p in o.photos
        ]
        price_str = f"{float(o.price):.2f}".rstrip("0").rstrip(".")
        payment_str = "❗ Не оплачен" if not o.paid else "✅ Оплачен"
        text += (
            f"🆔 <code>{o.order_id[:8]}</code>  📅 {o.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"🖼 Фото: {len(o.photos)} шт.\n"
            + "\n".join(photo_lines) + "\n"
            f"💰 {price_str} ₽ — {payment_str}\n"
            f"📍 {o.delivery_point or 'Пункт не выбран'}\n"
            f"👤 Получатель: {o.receiver_name or '—'}\n"
            f"📞 Телефон: {o.receiver_phone or '—'}\n"
            f"💬 {o.comment or '—'}\n\n"
        )
        # Изменить / Отменить
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="✏ Изменить", callback_data=f"edit:{o.order_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel:{o.order_id}")
        ])
        # Кнопка оплаты, если не оплачено
        if not o.paid:
            kb.inline_keyboard.append([
                InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay:{o.order_id}")
            ])

    # Навигация
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="page:prev"),
        InlineKeyboardButton(text="➡ Далее", callback_data="page:next")
    ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 К категориям", callback_data="back:status")
    ])

    await message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

def register_orders_handlers(dp: Dispatcher):
    @dp.message(F.text == "📦 Мои заказы")
    async def choose_status(message: Message, state: FSMContext):
        db = SessionLocal()
        statuses = db.query(OrderStatus).order_by(OrderStatus.sort_order).all()
        db.close()
        kb_rows = [[InlineKeyboardButton(text=s.label, callback_data=f"status:{s.code}")] for s in statuses]
        await message.answer(
            "📦 Выберите категорию заказов:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
        )
        await state.set_state(OrdersFSM.choosing_status)

    @dp.callback_query(F.data.startswith("status:"), OrdersFSM.choosing_status)
    async def show_orders_by_status(callback_query: CallbackQuery, state: FSMContext):
        status_code = callback_query.data.split(":", 1)[1]
        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=callback_query.from_user.id).first()
        status = db.query(OrderStatus).filter_by(code=status_code).first()
        orders = (
            db.query(Order)
            .filter_by(user_id=user.id, status=status_code)
            .order_by(desc(Order.created_at))
            .limit(3)
            .all()
        )
        db.close()

        if not orders:
            await callback_query.message.edit_text("❗ Заказы не найдены в этой категории.")
            await state.clear()
            return

        await state.update_data(status_filter=status_code, page=0)
        await _send_orders_list(callback_query.message, orders, status.label, 0)
        await state.set_state(OrdersFSM.browsing_orders)

    @dp.callback_query(F.data.startswith("pay:"), OrdersFSM.browsing_orders)
    async def pay_order(callback_query: CallbackQuery, state: FSMContext):
        order_id = callback_query.data.split(":",1)[1]
        db = SessionLocal()
        order = db.query(Order).filter_by(order_id=order_id).first()
        if order and not order.paid:
            order.paid = True
            db.commit()
            await callback_query.answer("✅ Заказ оплачен.", show_alert=True)
        else:
            await callback_query.answer("❗ Невозможно оплатить этот заказ.", show_alert=True)

        # Обновляем список на той же странице
        data = await state.get_data()
        status_code = data.get("status_filter")
        page = data.get("page", 0)
        user = db.query(User).filter_by(telegram_id=callback_query.from_user.id).first()
        orders = (
            db.query(Order)
            .filter_by(user_id=user.id, status=status_code)
            .order_by(desc(Order.created_at))
            .offset(page * 1)
            .limit(1)
            .all()
        )
        status_label = db.query(OrderStatus).filter_by(code=status_code).first().label
        db.close()
        await _send_orders_list(callback_query.message, orders, status_label, page)

    @dp.callback_query(F.data == "back:status")
    async def back_to_status(callback_query: CallbackQuery, state: FSMContext):
        db = SessionLocal()
        statuses = db.query(OrderStatus).order_by(OrderStatus.sort_order).all()
        db.close()
        kb_rows = [[InlineKeyboardButton(text=s.label, callback_data=f"status:{s.code}")] for s in statuses]
        await callback_query.message.edit_text(
            "📦 Выберите категорию заказов:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
        )
        await state.set_state(OrdersFSM.choosing_status)
        await callback_query.answer()

    @dp.callback_query(F.data.startswith("page:"), OrdersFSM.browsing_orders)
    async def paginate_orders(callback_query: CallbackQuery, state: FSMContext):
        direction = callback_query.data.split(":",1)[1]
        data = await state.get_data()
        status_code = data.get("status_filter")
        page = data.get("page",0)
        new_page = max(page-1,0) if direction=="prev" else page+1

        db = SessionLocal()
        user = db.query(User).filter_by(telegram_id=callback_query.from_user.id).first()
        status = db.query(OrderStatus).filter_by(code=status_code).first()
        orders = (
            db.query(Order)
            .filter_by(user_id=user.id, status=status_code)
            .order_by(desc(Order.created_at))
            .offset(new_page*1)
            .limit(1)
            .all()
        )
        db.close()
        if not orders:
            await callback_query.answer("Больше нет заказов.", show_alert=True)
            return
        await state.update_data(page=new_page)
        await _send_orders_list(callback_query.message, orders, status.label, new_page)
        await callback_query.answer()

    @dp.callback_query(F.data.startswith("cancel:"), OrdersFSM.browsing_orders)
    async def cancel_order_callback(callback_query: CallbackQuery, state: FSMContext):
        order_id = callback_query.data.split(":",1)[1]
        db = SessionLocal()
        order = db.query(Order).filter_by(order_id=order_id).first()
        user = db.query(User).filter_by(telegram_id=callback_query.from_user.id).first()
        if order:
            folder = f"uploads/{user.telegram_id}/{order.order_id}"
            if os.path.exists(folder): shutil.rmtree(folder)
            db.delete(order)
            db.commit()
            # Обновляем список
            data = await state.get_data()
            status_code = data.get("status_filter")
            page = data.get("page",0)
            status = db.query(OrderStatus).filter_by(code=status_code).first()
            orders = (
                db.query(Order)
                .filter_by(user_id=user.id, status=status_code)
                .order_by(desc(Order.created_at))
                .offset(page*1)
                .limit(1)
                .all()
            )
            db.close()
            await callback_query.answer("Заказ отменён.", show_alert=True)
            if orders:
                await _send_orders_list(callback_query.message, orders, status.label, page)
            else:
                db2 = SessionLocal()
                statuses = db2.query(OrderStatus).order_by(OrderStatus.sort_order).all()
                db2.close()
                kb_rows = [[InlineKeyboardButton(text=s.label, callback_data=f"status:{s.code}")] for s in statuses]
                await callback_query.message.edit_text(
                    "❗ Заказы не найдены в этой категории.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
                )
                await state.set_state(OrdersFSM.choosing_status)
        else:
            db.close()
            await callback_query.answer("❗ Заказ не найден.", show_alert=True)

            return

        await state.update_data(editing_order_id=order_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📞 Телефон получателя", callback_data="editfield:receiver_phone")],
            [InlineKeyboardButton(text="👤 ФИО получателя",    callback_data="editfield:receiver_name")]
        ])
        if order.status == 'new':
            kb.inline_keyboard += [
                [InlineKeyboardButton(text="🖼 Формат",         callback_data="editfield:format")],
                [InlineKeyboardButton(text="🔢 Кол-во копий",   callback_data="editfield:copies")],
                [InlineKeyboardButton(text="📍 Изменить ПВЗ",   callback_data=f"editpp:{order_id}")]
            ]
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="✅ Сохранить изменения", callback_data="back:status"),
            InlineKeyboardButton(text="❌ Отменить редактирование", callback_data="back:status")
        ])
        await callback_query.message.answer(
            f"Что вы хотите изменить для заказа #{order_id[:8]}?",
            reply_markup=kb
        )
        await state.set_state(OrdersFSM.editing_field_choice)

    @dp.callback_query(F.data.startswith("editfield:"), OrdersFSM.editing_field_choice)
    async def ask_new_value(callback_query: CallbackQuery, state: FSMContext):
        field = callback_query.data.split(":", 1)[1]
        await state.update_data(editing_field=field)
        if field == 'format':
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=fmt, callback_data=f"setformat:{fmt}")] for fmt in FORMATS
            ])
            await callback_query.message.answer("Выберите формат:", reply_markup=kb)
        else:
            prompts = {
                'receiver_phone': 'Введите новый номер телефона получателя:',
                'receiver_name':  'Введите новое ФИО получателя:',
                'copies':         'Введите новое количество копий:'
            }
            await callback_query.message.answer(prompts[field])
            await state.set_state(OrdersFSM.editing_value_input)

    @dp.callback_query(F.data.startswith("setformat:"), OrdersFSM.editing_field_choice)
    async def set_format_from_button(callback_query: CallbackQuery, state: FSMContext):
        fmt = callback_query.data.split(":", 1)[1]
        await state.update_data(editing_field='format', editing_value=fmt)
        await _apply_edit_common(callback_query.message, state)

    @dp.message(OrdersFSM.editing_value_input)
    async def apply_edit_text(message: Message, state: FSMContext):
        await state.update_data(editing_value=message.text.strip())
        await _apply_edit_common(message, state)

    async def _apply_edit_common(source_msg: Message, state: FSMContext):
        data = await state.get_data()
        order_id = data['editing_order_id']
        field    = data['editing_field']
        new_value= data['editing_value']

        db = SessionLocal()
        order = db.query(Order).filter_by(order_id=order_id).first()
        if not order:
            await source_msg.answer("❗ Заказ не найден.")
            db.close()
            await state.clear()
            return

        if field == 'receiver_phone':
            order.receiver_phone = new_value
        elif field == 'receiver_name':
            order.receiver_name = new_value
        elif field == 'format' and order.status == 'new':
            for photo in order.photos:
                photo['format'] = new_value
            flag_modified(order, 'photos')
        elif field == 'copies' and order.status == 'new':
            try:
                cnt = int(new_value)
                for photo in order.photos:
                    photo['copies'] = cnt
                flag_modified(order, 'photos')
            except ValueError:
                await source_msg.answer("❗ Введите корректное число.")
                db.close()
                return

        db.commit()
        updated = db.query(Order).filter_by(order_id=order_id).first()
        db.close()

        # подготовка и отправка финального сообщения с кнопками
        photo_lines = [
            f"• {p['filename']} — {p['format']}, {p['copies']} коп."
            for p in updated.photos
        ]
        res_text = (
            f"<b>✅ Изменения сохранены</b>\n\n"
            + f"🆔 <code>{updated.order_id[:8]}</code>  📅 {updated.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            + f"🖼 Фото: {len(updated.photos)} шт.\n"
            + "\n".join(photo_lines) + "\n"
            + f"💰 {float(updated.price):.2f} ₽\n"
            + f"📍 {updated.delivery_point or 'Пункт не выбран'}\n"
            + f"👤 {updated.receiver_name or '—'}\n"
            + f"📞 {updated.receiver_phone or '—'}\n"
            + f"💬 {updated.comment or '—'}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продолжить редактирование", callback_data=f"edit:{order_id}")],
            [InlineKeyboardButton(text="✅ Готово",                    callback_data="back:status")]
        ])
        await source_msg.answer(res_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await state.clear()

    @dp.callback_query(F.data.startswith("editpp:"), OrdersFSM.editing_field_choice)
    async def edit_pickup(callback_query: CallbackQuery, state: FSMContext):
        order_id = callback_query.data.split(":", 1)[1]
        db = SessionLocal()
        points = db.query(PickupPoint).all()
        db.close()
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        for p in points:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"{p.name} — {p.address}",
                    callback_data=f"setpp:{order_id}:{p.id}"
                )
            ])
        await callback_query.message.answer("Выберите новый ПВЗ:", reply_markup=kb)
        await state.update_data(editing_order_id=order_id)
        await state.set_state(OrdersFSM.editing_pickup)
        await callback_query.answer()

    @dp.callback_query(F.data.startswith("setpp:"), OrdersFSM.editing_pickup)
    async def set_pickup(callback_query: CallbackQuery, state: FSMContext):
        _, order_id, pp_id = callback_query.data.split(":")
        pp_id = int(pp_id)
        db = SessionLocal()
        pickup = db.query(PickupPoint).filter_by(id=pp_id).first()
        order = db.query(Order).filter_by(order_id=order_id).first()

        if order and order.status == get_status_code(db, "Новый"):
            order.delivery_point = pickup.name
            db.commit()
            # повторяем логику _apply_edit_common для ПВЗ
            updated = order
            photo_lines = [
                f"• {p['filename']} — {p['format']}, {p['copies']} коп."
                for p in updated.photos
            ]
            res_text = (
                f"<b>✅ Изменения сохранены</b>\n\n"
                + f"🆔 <code>{updated.order_id[:8]}</code>  📅 {updated.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                + f"🖼 Фото: {len(updated.photos)} шт.\n"
                + "\n".join(photo_lines) + "\n"
                + f"💰 {float(updated.price):.2f} ₽\n"
                + f"📍 {updated.delivery_point}\n"
                + f"👤 {updated.receiver_name or '—'}\n"
                + f"📞 {updated.receiver_phone or '—'}\n"
                + f"💬 {updated.comment or '—'}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Продолжить редактирование", callback_data=f"edit:{order_id}")],
                [InlineKeyboardButton(text="✅ Готово",                    callback_data="back:status")]
            ])
            await callback_query.message.answer(res_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await callback_query.message.answer("Нельзя изменить ПВЗ для этого заказа.")

        db.close()
        await state.clear()
