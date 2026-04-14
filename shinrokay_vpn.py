#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import logging
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import aiohttp

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7586800086:AAEl5MHe0zJiQJRtDfKmLYkCvlPiB4GIekk"
ADMIN_IDS = [8346538289, 5710669472]
YOOMONEY_ACCESS_TOKEN = "4100118889570559.3288B2E716CEEB922A26BD6BEAC58648FBFB680CCF64E4E1447D714D6FB5EA5F01F1478FAC686BEF394C8A186C98982DE563C1ABCDF9F2F61D971B61DA3C7E486CA818F98B9E0069F1C0891E090DD56A11319D626A40F0AE8302A8339DED9EB7969617F191D93275F64C4127A3ECB7AED33FCDE91CA68690EB7534C67E6C219E"
YOOMONEY_WALLET = "4100118889570559"

DB_NAME = "vpn_bot.db"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            registration_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vpn_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_name TEXT,
            config_data TEXT,
            category_id INTEGER,
            is_sold INTEGER DEFAULT 0,
            added_date TEXT,
            FOREIGN KEY (category_id) REFERENCES vpn_categories(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vpn_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            duration_days INTEGER,
            description TEXT,
            features TEXT,
            emoji TEXT,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            config_id INTEGER,
            payment_id TEXT,
            amount REAL,
            purchase_date TEXT,
            expiry_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (config_id) REFERENCES vpn_configs(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            category_id INTEGER,
            status TEXT,
            created_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Добавляем дефолтные категории VPN
    cursor.execute("SELECT COUNT(*) FROM vpn_categories")
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ("BABY VPN", 139.0, 30, "Базовый VPN для начинающих", 
             "• Стабилизация урона\n• Стабилизация пинга\n• 24-30ms без скачков\n• Точность пуль\n• Без бана\n• Макс.урон\n• Макс.отклик\n• Пустой сервер",
             "👶", 1),
            
            ("ME VPN", 279.0, 30, "Продвинутый VPN с улучшенным регом",
             "• Улучшенный рег в голову и тело\n• Стабильный пинг 20-24ms\n• Быстрая и плавная игра\n• Резкий сбрив противника\n• Телепорты от противника\n• Для турниров\n• Подробный гайд",
             "⚡", 2),
            
            ("LAYF VPN", 390.0, 30, "VPN с максимальным регом",
             "• Максимальный рег в голову и тело\n• Стабильный пинг 12-20ms\n• Быстрая и плавная игра\n• Резкий сбрив противника\n• Телепорты от противника\n• Лучшая оптимизация\n• Для турниров",
             "🔥", 3),
            
            ("STRONG VPN", 499.0, 30, "Мощный VPN без бана",
             "• Максимальный рег в голову и тело\n• Стабильный пинг 12-20ms\n• Быстрая и плавная игра\n• Резкий сбрив противника\n• Телепорты от противника\n• Лучшая оптимизация\n• Для турниров\n• Без бана\n• Лучший рег и быстрый сбрив",
             "💪", 4),
            
            ("SUPER VPN", 585.0, 30, "Супер VPN с лютым регом",
             "• Пинг 20-24ms\n• Стабильно 2-3 головы\n• Лютые лаги у противника\n• Плавность устройства\n• Лютые сбривы\n• Ебанутая регистрация урона\n• Для всех режимов",
             "🚀", 5),
            
            ("VPN DRAYF", 899.0, 30, "Топовый VPN для профи",
             "• Стабильный пинг 20ms\n• Быстрая игра на плавности\n• Быстрые сбривы противника\n• Телепорты от противника\n• Для турниров\n• Максимальный рег\n• Улучшенный рег в голову и тело\n• Быстрая и плавная игра",
             "👑", 6),
        ]
        
        cursor.executemany(
            "INSERT INTO vpn_categories (name, price, duration_days, description, features, emoji, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
            default_categories
        )
    
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, registration_date) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def add_vpn_config(config_name: str, config_data: str, category_id: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO vpn_configs (config_name, config_data, category_id, added_date) VALUES (?, ?, ?, ?)",
        (config_name, config_data, category_id, datetime.now().isoformat())
    )
    config_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return config_id

def get_available_config_by_category(category_id: int) -> Optional[tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, config_name, config_data FROM vpn_configs WHERE category_id = ? AND is_sold = 0 LIMIT 1",
        (category_id,)
    )
    config = cursor.fetchone()
    conn.close()
    return config

def mark_config_as_sold(config_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE vpn_configs SET is_sold = 1 WHERE id = ?", (config_id,))
    conn.commit()
    conn.close()

def get_available_configs_count_by_category(category_id: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vpn_configs WHERE category_id = ? AND is_sold = 0", (category_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_vpn_categories() -> List[tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, duration_days, description, features, emoji FROM vpn_categories ORDER BY sort_order")
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_category_by_id(category_id: int) -> Optional[tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, duration_days, description, features, emoji FROM vpn_categories WHERE id = ?", (category_id,))
    category = cursor.fetchone()
    conn.close()
    return category

def add_category(name: str, price: float, duration_days: int, description: str, features: str, emoji: str) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM vpn_categories")
    sort_order = cursor.fetchone()[0]
    
    cursor.execute(
        "INSERT INTO vpn_categories (name, price, duration_days, description, features, emoji, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, price, duration_days, description, features, emoji, sort_order)
    )
    category_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return category_id

def delete_category(category_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vpn_categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()

def add_purchase(user_id: int, config_id: int, payment_id: str, amount: float, duration_days: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    purchase_date = datetime.now()
    expiry_date = purchase_date + timedelta(days=duration_days)
    
    cursor.execute(
        "INSERT INTO purchases (user_id, config_id, payment_id, amount, purchase_date, expiry_date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, config_id, payment_id, amount, purchase_date.isoformat(), expiry_date.isoformat())
    )
    conn.commit()
    conn.close()

def create_payment(user_id: int, amount: float, category_id: int) -> str:
    payment_id = str(uuid.uuid4())[:8].upper()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (payment_id, user_id, amount, category_id, status, created_date) VALUES (?, ?, ?, ?, ?, ?)",
        (payment_id, user_id, amount, category_id, 'pending', datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return payment_id

def get_payment(payment_id: str) -> Optional[tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT payment_id, user_id, amount, category_id, status FROM payments WHERE payment_id = ?",
        (payment_id,)
    )
    payment = cursor.fetchone()
    conn.close()
    return payment

def update_payment_status(payment_id: str, status: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE payments SET status = ? WHERE payment_id = ?", (status, payment_id))
    conn.commit()
    conn.close()

def get_user_purchases(user_id: int) -> List[tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.id, p.purchase_date, p.expiry_date, p.amount, v.config_name, c.name, c.emoji
        FROM purchases p
        JOIN vpn_configs v ON p.config_id = v.id
        JOIN vpn_categories c ON v.category_id = c.id
        WHERE p.user_id = ?
        ORDER BY p.purchase_date DESC
        """,
        (user_id,)
    )
    purchases = cursor.fetchall()
    conn.close()
    return purchases

def get_stats() -> dict:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM vpn_configs WHERE is_sold = 0")
    available_configs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM vpn_configs WHERE is_sold = 1")
    sold_configs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM purchases")
    total_purchases = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount) FROM purchases")
    total_revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_users': total_users,
        'available_configs': available_configs,
        'sold_configs': sold_configs,
        'total_purchases': total_purchases,
        'total_revenue': total_revenue
    }

# ==================== YOOMONEY ====================
async def create_yoomoney_payment(amount: float, label: str) -> str:
    payment_url = (
        f"https://yoomoney.ru/quickpay/confirm.xml?"
        f"receiver={YOOMONEY_WALLET}&"
        f"quickpay-form=shop&"
        f"targets=VPN+PUBG+{label}&"
        f"paymentType=SB&"
        f"sum={amount}&"
        f"label={label}&"
        f"comment={label}&"
        f"successURL=https://t.me/ShinRokayVPN_bot"
    )
    return payment_url

async def check_payment_yoomoney(label: str, amount: float) -> bool:
    url = "https://yoomoney.ru/api/operation-history"
    
    headers = {
        "Authorization": f"Bearer {YOOMONEY_ACCESS_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    params = {"records": "30"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=params) as response:
                if response.status == 200:
                    result = await response.json()
                    operations = result.get('operations', [])
                    
                    for operation in operations:
                        op_label = operation.get('label', '')
                        op_amount = float(operation.get('amount', 0))
                        op_status = operation.get('status', '')
                        op_direction = operation.get('direction', '')
                        
                        if (op_label == label and 
                            op_status == 'success' and
                            op_direction == 'in' and
                            op_amount >= amount):
                            return True
                            
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        return False

# ==================== ОБРАБОТЧИКИ ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or "", user.first_name or "")
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("📋 Мои покупки", callback_data="my_purchases")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton("💬 Поддержка", url="https://t.me/metigiev_102")]
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🎮 Добро пожаловать в <b>𝑺𝒉𝒊𝒏𝑹𝒐𝒌𝒂𝒚 VPN Bot</b>!\n\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"🔐 Профессиональные VPN для PUBG Mobile\n"
        f"⚡ Низкий пинг и максимальный рег\n"
        f"🎯 Подходит для турниров\n\n"
        f"✨ Выберите действие:"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "buy_vpn":
        await show_categories(query)
    elif data == "my_purchases":
        await show_my_purchases(query, user_id)
    elif data == "info":
        await show_info(query)
    elif data == "admin_panel" and user_id in ADMIN_IDS:
        await show_admin_panel(query)
    elif data.startswith("category_"):
        category_id = int(data.split("_")[1])
        await show_category_details(query, category_id)
    elif data.startswith("buy_category_"):
        category_id = int(data.split("_")[2])
        await process_category_purchase(query, context, user_id, category_id)
    elif data.startswith("check_payment_"):
        payment_id = data.split("_", 2)[2]
        await check_payment_manual(query, context, user_id, payment_id)
    elif data.startswith("confirm_payment_"):
        if user_id in ADMIN_IDS:
            payment_id = data.split("_", 2)[2]
            await confirm_payment_admin(query, context, payment_id)
    elif data == "admin_add_config" and user_id in ADMIN_IDS:
        await show_categories_for_config(query, context)
    elif data.startswith("add_config_cat_") and user_id in ADMIN_IDS:
        category_id = int(data.split("_")[3])
        context.user_data['adding_config_category'] = category_id
        await query.message.reply_text("📁 Отправьте .conf файл или /cancel")
        context.user_data['awaiting_config'] = True
    elif data == "admin_stats" and user_id in ADMIN_IDS:
        await show_admin_stats(query)
    elif data == "admin_configs" and user_id in ADMIN_IDS:
        await show_admin_configs(query)
    elif data == "admin_categories" and user_id in ADMIN_IDS:
        await show_admin_categories(query)
    elif data == "admin_add_category" and user_id in ADMIN_IDS:
        await start_add_category(query, context)
    elif data == "admin_pending_payments" and user_id in ADMIN_IDS:
        await show_pending_payments(query, context)
    elif data.startswith("admin_delete_cat_") and user_id in ADMIN_IDS:
        category_id = int(data.split("_")[3])
        await delete_category_confirm(query, category_id)
    elif data.startswith("confirm_delete_cat_") and user_id in ADMIN_IDS:
        category_id = int(data.split("_")[3])
        delete_category(category_id)
        await query.message.edit_text("✅ Категория удалена!")
        await asyncio.sleep(1)
        await show_admin_categories(query)
    elif data == "back_to_menu":
        await back_to_menu(query)
    elif data == "back_to_categories":
        await show_categories(query)
    elif data == "back_to_admin":
        await show_admin_panel(query)

async def show_categories(query):
    categories = get_vpn_categories()
    
    if not categories:
        await query.message.edit_text(
            "❌ Категории VPN пока не добавлены.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]])
        )
        return
    
    text = "🎮 <b>Выберите категорию VPN:</b>\n\n"
    
    keyboard = []
    for cat_id, name, price, duration_days, description, _, emoji in categories:
        available = get_available_configs_count_by_category(cat_id)
        status = f"✅ {available} шт." if available > 0 else "❌ Нет в наличии"
        
        text += f"{emoji} <b>{name}</b> - {price} ₽\n   {description}\n   {status}\n\n"
        
        if available > 0:
            keyboard.append([InlineKeyboardButton(f"{emoji} {name} - {price} ₽", callback_data=f"category_{cat_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_category_details(query, category_id: int):
    category = get_category_by_id(category_id)
    if not category:
        await query.answer("❌ Категория не найдена")
        return
    
    cat_id, name, price, duration_days, description, features, emoji = category
    available = get_available_configs_count_by_category(cat_id)
    
    text = (
        f"{emoji} <b>{name}</b>\n\n"
        f"💰 Цена: <b>{price} ₽</b>\n"
        f"📅 Срок: <b>{duration_days} дней</b>\n"
        f"📦 Доступно: <b>{available} шт.</b>\n\n"
        f"📝 <b>Описание:</b>\n{description}\n\n"
        f"✨ <b>Что дает:</b>\n{features}\n\n"
        f"📱 Поддержка: Android / iOS / iPad"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"💳 Купить за {price} ₽", callback_data=f"buy_category_{cat_id}")],
        [InlineKeyboardButton("◀️ Назад к категориям", callback_data="back_to_categories")]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def process_category_purchase(query, context: ContextTypes.DEFAULT_TYPE, user_id: int, category_id: int):
    category = get_category_by_id(category_id)
    if not category:
        await query.answer("❌ Категория не найдена")
        return
    
    cat_id, name, price, duration_days, description, features, emoji = category
    
    config = get_available_config_by_category(cat_id)
    if not config:
        await query.message.edit_text(
            f"❌ К сожалению, конфигурации <b>{name}</b> закончились.\n\nПопробуйте выбрать другую категорию.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_categories")]]),
            parse_mode='HTML'
        )
        return
    
    payment_id = create_payment(user_id, price, cat_id)
    
    context.user_data[f'payment_{payment_id}'] = {
        'category_id': cat_id,
        'duration_days': duration_days,
        'price': price,
        'config_id': config[0]
    }
    
    payment_url = await create_yoomoney_payment(price, payment_id)
    
    text = (
        f"💳 <b>Оплата {name}</b>\n\n"
        f"{emoji} Категория: <b>{name}</b>\n"
        f"💰 Сумма: <b>{price} ₽</b>\n"
        f"⏱ Срок: <b>{duration_days} дней</b>\n\n"
        f"🔑 <b>Код платежа (автоматически вставлен):</b>\n"
        f"<code>{payment_id}</code>\n\n"
        f"📝 <b>Инструкция по оплате:</b>\n"
        f"1️⃣ Нажмите кнопку 'Оплатить'\n"
        f"2️⃣ Переведите <b>РОВНО {price} ₽</b>\n"
        f"3️⃣ Код <code>{payment_id}</code> уже вставлен в комментарий\n"
        f"4️⃣ Подтвердите платеж\n"
        f"5️⃣ Вернитесь сюда и нажмите 'Я оплатил'\n\n"
        f"⚠️ <b>ВАЖНО:</b> Не меняйте сумму и комментарий!"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить (код уже вставлен)", url=payment_url)],
        [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment_{payment_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_categories")]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            admin_keyboard = [[InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_payment_{payment_id}")]]
            await context.bot.send_message(
                admin_id,
                f"💰 <b>Новый платеж!</b>\n\n"
                f"👤 {query.from_user.first_name} (@{query.from_user.username or 'нет'})\n"
                f"{emoji} Категория: <b>{name}</b>\n"
                f"💵 Сумма: <b>{price} ₽</b>\n"
                f"🔑 Код: <code>{payment_id}</code>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(admin_keyboard)
            )
        except:
            pass

async def check_payment_manual(query, context: ContextTypes.DEFAULT_TYPE, user_id: int, payment_id: str):
    await query.answer("🔄 Проверяем оплату...")
    
    payment_data = context.user_data.get(f'payment_{payment_id}')
    if not payment_data:
        await query.answer("❌ Данные не найдены", show_alert=True)
        return
    
    is_paid = await check_payment_yoomoney(payment_id, payment_data['price'])
    
    if is_paid:
        await process_successful_payment(context, query, user_id, payment_id, payment_data)
    else:
        await query.answer(
            "❌ Оплата не найдена.\n\n"
            "Проверьте:\n"
            f"• Сумма: {payment_data['price']} ₽\n"
            f"• Код: {payment_id}\n\n"
            "Или нажмите 'Подтвердить' для связи с поддержкой.",
            show_alert=True
        )

async def confirm_payment_admin(query, context: ContextTypes.DEFAULT_TYPE, payment_id: str):
    payment = get_payment(payment_id)
    if not payment:
        await query.answer("❌ Платеж не найден")
        return
    
    _, user_id, amount, category_id, status = payment
    
    if status == 'completed':
        await query.answer("✅ Платеж уже подтвержден")
        return
    
    category = get_category_by_id(category_id)
    if not category:
        await query.answer("❌ Категория не найдена")
        return
    
    _, name, _, duration_days, _, _, emoji = category
    
    config = get_available_config_by_category(category_id)
    if not config:
        await query.answer("❌ Нет доступных конфигов")
        return
    
    config_id, config_name, config_data = config
    
    add_purchase(user_id, config_id, payment_id, amount, duration_days)
    mark_config_as_sold(config_id)
    update_payment_status(payment_id, 'completed')
    
    try:
        success_text = (
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"🎉 Спасибо за покупку {emoji} <b>{name}</b>!\n\n"
            f"📁 Ваш VPN конфиг отправлен ниже.\n\n"
            f"📝 <b>Инструкция:</b>\n"
            f"1. Установите WireGuard из App Store/Google Play\n"
            f"2. Откройте приложение\n"
            f"3. Нажмите '+' и выберите файл\n"
            f"4. Выберите отправленный .conf файл\n"
            f"5. Активируйте подключение\n\n"
            f"💬 Вопросы? Пишите: @metigiev_102"
        )
        
        await context.bot.send_message(user_id, success_text, parse_mode='HTML')
        
        config_file = BytesIO(config_data.encode('utf-8'))
        config_file.name = config_name
        
        await context.bot.send_document(
            user_id,
            document=config_file,
            filename=config_name,
            caption=f"{emoji} <b>{name}</b>\n📁 {config_name}",
            parse_mode='HTML'
        )
        
        await query.message.edit_text(
            f"✅ <b>Платеж подтвержден!</b>\n\n"
            f"Конфиг отправлен пользователю.",
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await query.answer("❌ Ошибка отправки")

async def process_successful_payment(context: ContextTypes.DEFAULT_TYPE, query, user_id: int, payment_id: str, payment_data: dict):
    config_id = payment_data['config_id']
    category_id = payment_data['category_id']
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT config_name, config_data FROM vpn_configs WHERE id = ?", (config_id,))
    config = cursor.fetchone()
    conn.close()
    
    if not config:
        await query.message.edit_text("❌ Конфиг не найден.")
        return
    
    config_name, config_data = config
    
    category = get_category_by_id(category_id)
    _, name, _, _, _, _, emoji = category
    
    add_purchase(user_id, config_id, payment_id, payment_data['price'], payment_data['duration_days'])
    mark_config_as_sold(config_id)
    update_payment_status(payment_id, 'completed')
    
    success_text = (
        f"✅ <b>Оплата подтверждена!</b>\n\n"
        f"🎉 Спасибо за покупку {emoji} <b>{name}</b>!\n\n"
        f"📝 <b>Инструкция:</b>\n"
        f"1. Установите WireGuard\n"
        f"2. Импортируйте файл ниже\n"
        f"3. Подключитесь\n\n"
        f"💬 Поддержка: @metigiev_102"
    )
    
    await query.message.edit_text(success_text, parse_mode='HTML')
    
    config_file = BytesIO(config_data.encode('utf-8'))
    config_file.name = config_name
    
    await query.message.reply_document(
        document=config_file,
        filename=config_name,
        caption=f"{emoji} <b>{name}</b>\n📁 {config_name}",
        parse_mode='HTML'
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"💰 <b>Продажа!</b>\n\n"
                f"👤 {query.from_user.first_name}\n"
                f"{emoji} {name}\n"
                f"💵 {payment_data['price']} ₽",
                parse_mode='HTML'
            )
        except:
            pass
    
    if f'payment_{payment_id}' in context.user_data:
        del context.user_data[f'payment_{payment_id}']

async def show_pending_payments(query, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.payment_id, p.user_id, p.amount, c.name, c.emoji, u.first_name, u.username
        FROM payments p
        JOIN vpn_categories c ON p.category_id = c.id
        JOIN users u ON p.user_id = u.user_id
        WHERE p.status = 'pending'
        ORDER BY p.created_date DESC
        LIMIT 10
    """)
    pending = cursor.fetchall()
    conn.close()
    
    if not pending:
        text = "✅ Нет ожидающих платежей"
    else:
        text = "⏳ <b>Ожидающие платежи:</b>\n\n"
        for payment_id, user_id, amount, cat_name, emoji, first_name, username in pending:
            text += f"🔹 <code>{payment_id}</code>\n"
            text += f"   👤 {first_name} (@{username or 'нет'})\n"
            text += f"   {emoji} {cat_name} - {amount} ₽\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_my_purchases(query, user_id: int):
    purchases = get_user_purchases(user_id)
    
    if not purchases:
        text = "📋 У вас пока нет покупок.\n\nПосмотрите наши VPN категории!"
        keyboard = [[InlineKeyboardButton("🛒 Купить VPN", callback_data="buy_vpn")]]
    else:
        text = "📋 <b>Ваши покупки:</b>\n\n"
        
        for _, purchase_date, expiry_date, amount, config_name, cat_name, emoji in purchases:
            purchase_dt = datetime.fromisoformat(purchase_date)
            expiry_dt = datetime.fromisoformat(expiry_date)
            days_left = (expiry_dt - datetime.now()).days
            
            status = "✅ Активен" if days_left > 0 else "❌ Истек"
            
            text += (
                f"{emoji} <b>{cat_name}</b>\n"
                f"   📁 {config_name}\n"
                f"   💰 {amount} ₽ | 📅 {purchase_dt.strftime('%d.%m.%Y')}\n"
                f"   ⏱ До: {expiry_dt.strftime('%d.%m.%Y')} | {status}"
            )
            
            if days_left > 0:
                text += f" ({days_left} дн.)\n\n"
            else:
                text += "\n\n"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_info(query):
    text = (
        "ℹ️ <b>𝑺𝒉𝒊𝒏𝑹𝒐𝒌𝒂𝒚 VPN Bot</b>\n\n"
        "🎮 <b>Профессиональные VPN для PUBG Mobile</b>\n\n"
        "✨ <b>Наши преимущества:</b>\n"
        "• 👶 От базовых до топовых конфигураций\n"
        "• ⚡ Пинг от 12ms до 30ms\n"
        "• 🎯 Максимальная регистрация урона\n"
        "• 🏆 Подходит для турниров\n"
        "• 🔒 Без бана\n"
        "• 💪 Стабильная работа\n"
        "• 📱 Android / iOS / iPad\n\n"
        "💰 <b>Оплата:</b> Рубли (₽), Гривны (₴), Stars (⭐)\n\n"
        "📞 <b>Поддержка:</b> @metigiev_102\n\n"
        "🎁 Выбирайте подходящую категорию и играйте на максимум!"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить конфиг", callback_data="admin_add_config")],
        [InlineKeyboardButton("⏳ Ожидающие платежи", callback_data="admin_pending_payments")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton("📂 Категории", callback_data="admin_categories")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]
    
    await query.message.edit_text("👨‍💼 <b>Админ панель</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_categories_for_config(query, context: ContextTypes.DEFAULT_TYPE):
    categories = get_vpn_categories()
    
    text = "📂 <b>Выберите категорию для конфига:</b>\n\n"
    keyboard = []
    
    for cat_id, name, _, _, _, _, emoji in categories:
        available = get_available_configs_count_by_category(cat_id)
        text += f"{emoji} {name} - {available} шт.\n"
        keyboard.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"add_config_cat_{cat_id}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_stats(query):
    stats = get_stats()
    
    # Статистика по категориям
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.name, c.emoji, COUNT(v.id) as total, SUM(CASE WHEN v.is_sold = 0 THEN 1 ELSE 0 END) as available
        FROM vpn_categories c
        LEFT JOIN vpn_configs v ON c.id = v.category_id
        GROUP BY c.id
        ORDER BY c.sort_order
    """)
    cat_stats = cursor.fetchall()
    conn.close()
    
    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"💳 Покупок: <b>{stats['total_purchases']}</b>\n"
        f"💰 Выручка: <b>{stats['total_revenue']:.0f} ₽</b>\n\n"
        f"📂 <b>По категориям:</b>\n\n"
    )
    
    for name, emoji, total, available in cat_stats:
        sold = total - (available or 0)
        text += f"{emoji} {name}:\n   📦 Всего: {total} | ✅ Доступно: {available or 0} | ✅ Продано: {sold}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_configs(query):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.config_name, v.is_sold, v.added_date, c.name, c.emoji
        FROM vpn_configs v
        JOIN vpn_categories c ON v.category_id = c.id
        ORDER BY v.added_date DESC
        LIMIT 20
    """)
    configs = cursor.fetchall()
    conn.close()
    
    if not configs:
        text = "📁 Конфигов нет."
    else:
        text = "📁 <b>Последние 20 конфигов:</b>\n\n"
        for config_name, is_sold, added_date, cat_name, emoji in configs:
            status = "❌ Продан" if is_sold else "✅ Доступен"
            date = datetime.fromisoformat(added_date).strftime('%d.%m %H:%M')
            text += f"{status} {emoji} {cat_name}\n   📄 {config_name} | {date}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_categories(query):
    categories = get_vpn_categories()
    
    text = "📂 <b>Категории VPN:</b>\n\n"
    keyboard = []
    
    if categories:
        for cat_id, name, price, duration_days, description, _, emoji in categories:
            available = get_available_configs_count_by_category(cat_id)
            text += f"{emoji} <b>{name}</b> - {price} ₽\n   {duration_days} дн. | Доступно: {available}\n   {description}\n\n"
            keyboard.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"admin_delete_cat_{cat_id}")])
    else:
        text += "Нет категорий.\n\n"
    
    keyboard.append([InlineKeyboardButton("➕ Добавить категорию", callback_data="admin_add_category")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def start_add_category(query, context: ContextTypes.DEFAULT_TYPE):
    await query.message.edit_text(
        "➕ <b>Новая категория VPN</b>\n\nВведите название (например: 'SUPER VPN'):\n\n/cancel - отмена",
        parse_mode='HTML'
    )
    context.user_data['adding_category'] = {}
    context.user_data['category_step'] = 'name'

async def delete_category_confirm(query, category_id: int):
    category = get_category_by_id(category_id)
    if not category:
        await query.answer("❌ Не найдена")
        return
    
    _, name, _, _, _, _, emoji = category
    
    keyboard = [
        [InlineKeyboardButton("✅ Удалить", callback_data=f"confirm_delete_cat_{category_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="admin_categories")]
    ]
    
    await query.message.edit_text(
        f"❓ Удалить категорию {emoji} <b>{name}</b>?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS or not context.user_data.get('awaiting_config'):
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.conf'):
        await update.message.reply_text("❌ Нужен .conf файл")
        return
    
    category_id = context.user_data.get('adding_config_category')
    if not category_id:
        await update.message.reply_text("❌ Категория не выбрана")
        return
    
    file = await context.bot.get_file(document.file_id)
    file_content = await file.download_as_bytearray()
    config_data = file_content.decode('utf-8')
    config_id = add_vpn_config(document.file_name, config_data, category_id)
    
    category = get_category_by_id(category_id)
    _, cat_name, _, _, _, _, emoji = category
    
    context.user_data['awaiting_config'] = False
    context.user_data.pop('adding_config_category', None)
    
    available = get_available_configs_count_by_category(category_id)
    
    await update.message.reply_text(
        f"✅ Конфиг добавлен!\n\n"
        f"{emoji} Категория: {cat_name}\n"
        f"📁 Файл: {document.file_name}\n"
        f"🆔 ID: {config_id}\n\n"
        f"📦 Всего в категории: {available}"
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    # Добавление категории
    if context.user_data.get('category_step'):
        step = context.user_data['category_step']
        category_data = context.user_data.get('adding_category', {})
        
        if step == 'name':
            category_data['name'] = update.message.text
            context.user_data['adding_category'] = category_data
            context.user_data['category_step'] = 'price'
            await update.message.reply_text("💰 Введите цену (например: 499):")
        
        elif step == 'price':
            try:
                category_data['price'] = float(update.message.text)
                context.user_data['adding_category'] = category_data
                context.user_data['category_step'] = 'days'
                await update.message.reply_text("📅 Введите дни (например: 30):")
            except:
                await update.message.reply_text("❌ Введите число!")
        
        elif step == 'days':
            try:
                category_data['days'] = int(update.message.text)
                context.user_data['adding_category'] = category_data
                context.user_data['category_step'] = 'description'
                await update.message.reply_text("📝 Введите краткое описание:")
            except:
                await update.message.reply_text("❌ Введите число!")
        
        elif step == 'description':
            category_data['description'] = update.message.text
            context.user_data['adding_category'] = category_data
            context.user_data['category_step'] = 'features'
            await update.message.reply_text(
                "✨ Введите особенности (каждая с новой строки, начинайте с •):\n\n"
                "Например:\n• Стабильный пинг\n• Макс.рег\n• Без бана"
            )
        
        elif step == 'features':
            category_data['features'] = update.message.text
            context.user_data['adding_category'] = category_data
            context.user_data['category_step'] = 'emoji'
            await update.message.reply_text("😊 Введите эмодзи для категории (например: 🔥):")
        
        elif step == 'emoji':
            category_data['emoji'] = update.message.text
            
            category_id = add_category(
                category_data['name'],
                category_data['price'],
                category_data['days'],
                category_data['description'],
                category_data['features'],
                category_data['emoji']
            )
            
            context.user_data.pop('adding_category', None)
            context.user_data.pop('category_step', None)
            
            await update.message.reply_text(
                f"✅ Категория создана!\n\n"
                f"{category_data['emoji']} {category_data['name']}\n"
                f"💰 {category_data['price']} ₽\n"
                f"📅 {category_data['days']} дн.\n"
                f"📝 {category_data['description']}"
            )

async def back_to_menu(query):
    user = query.from_user
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("📋 Мои покупки", callback_data="my_purchases")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton("💬 Поддержка", url="https://t.me/metigiev_102")]
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ", callback_data="admin_panel")])
    
    await query.message.edit_text(
        f"🎮 <b>𝑺𝒉𝒊𝒏𝑹𝒐𝒌𝒂𝒚 VPN</b>\n\n✨ Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено")

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    logger.info("🚀 Бот запущен с категориями VPN!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
