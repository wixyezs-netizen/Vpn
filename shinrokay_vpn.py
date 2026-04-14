#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import logging
import asyncio
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters
)

import aiohttp
import json

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "7586800086:AAEl5MHe0zJiQJRtDfKmLYkCvlPiB4GIekk"
ADMIN_IDS = [8346538289, 5710669472]
YOOMONEY_ACCESS_TOKEN = "4100118889570559.3288B2E716CEEB922A26BD6BEAC58648FBFB680CCF64E4E1447D714D6FB5EA5F01F1478FAC686BEF394C8A186C98982DE563C1ABCDF9F2F61D971B61DA3C7E486CA818F98B9E0069F1C0891E090DD56A11319D626A40F0AE8302A8339DED9EB7969617F191D93275F64C4127A3ECB7AED33FCDE91CA68690EB7534C67E6C219E"
YOOMONEY_WALLET = "4100118889570559"

DB_NAME = "vpn_bot.db"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            registration_date TEXT
        )
    ''')
    
    # Таблица конфигов VPN
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vpn_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_name TEXT,
            config_data TEXT,
            is_sold INTEGER DEFAULT 0,
            added_date TEXT
        )
    ''')
    
    # Таблица покупок
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
    
    # Таблица платежей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            status TEXT,
            created_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Таблица тарифов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            duration_days INTEGER,
            price REAL,
            description TEXT
        )
    ''')
    
    # Добавляем дефолтные тарифы если их нет
    cursor.execute("SELECT COUNT(*) FROM tariffs")
    if cursor.fetchone()[0] == 0:
        default_tariffs = [
            ("1 месяц", 30, 150.0, "VPN на 1 месяц для PUBG"),
            ("3 месяца", 90, 400.0, "VPN на 3 месяца для PUBG (скидка 11%)"),
            ("6 месяцев", 180, 750.0, "VPN на 6 месяцев для PUBG (скидка 17%)")
        ]
        cursor.executemany(
            "INSERT INTO tariffs (name, duration_days, price, description) VALUES (?, ?, ?, ?)",
            default_tariffs
        )
    
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str):
    """Добавление нового пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, registration_date) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def add_vpn_config(config_name: str, config_data: str) -> int:
    """Добавление VPN конфига"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO vpn_configs (config_name, config_data, added_date) VALUES (?, ?, ?)",
        (config_name, config_data, datetime.now().isoformat())
    )
    config_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return config_id

def get_available_config() -> Optional[tuple]:
    """Получение доступного конфига"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, config_name, config_data FROM vpn_configs WHERE is_sold = 0 LIMIT 1"
    )
    config = cursor.fetchone()
    conn.close()
    return config

def mark_config_as_sold(config_id: int):
    """Пометить конфиг как проданный"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE vpn_configs SET is_sold = 1 WHERE id = ?",
        (config_id,)
    )
    conn.commit()
    conn.close()

def get_available_configs_count() -> int:
    """Получить количество доступных конфигов"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vpn_configs WHERE is_sold = 0")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_tariffs() -> List[tuple]:
    """Получить все тарифы"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, duration_days, price, description FROM tariffs")
    tariffs = cursor.fetchall()
    conn.close()
    return tariffs

def add_purchase(user_id: int, config_id: int, payment_id: str, amount: float, duration_days: int):
    """Добавить покупку"""
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

def create_payment(user_id: int, amount: float) -> str:
    """Создать платеж"""
    payment_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (payment_id, user_id, amount, status, created_date) VALUES (?, ?, ?, ?, ?)",
        (payment_id, user_id, amount, 'pending', datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return payment_id

def update_payment_status(payment_id: str, status: str):
    """Обновить статус платежа"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE payments SET status = ? WHERE payment_id = ?",
        (status, payment_id)
    )
    conn.commit()
    conn.close()

def get_user_purchases(user_id: int) -> List[tuple]:
    """Получить покупки пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.id, p.purchase_date, p.expiry_date, p.amount, v.config_name
        FROM purchases p
        JOIN vpn_configs v ON p.config_id = v.id
        WHERE p.user_id = ?
        ORDER BY p.purchase_date DESC
        """,
        (user_id,)
    )
    purchases = cursor.fetchall()
    conn.close()
    return purchases

def get_stats() -> dict:
    """Получить статистику"""
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
async def create_yoomoney_payment(amount: float, label: str) -> Optional[str]:
    """Создать платеж YooMoney"""
    url = "https://yoomoney.ru/quickpay/confirm.xml"
    
    # Формируем ссылку на оплату
    payment_url = (
        f"https://yoomoney.ru/quickpay/confirm.xml?"
        f"receiver={YOOMONEY_WALLET}&"
        f"quickpay-form=shop&"
        f"targets=VPN для PUBG&"
        f"paymentType=SB&"
        f"sum={amount}&"
        f"label={label}"
    )
    
    return payment_url

async def check_payment_status(label: str) -> bool:
    """Проверить статус платежа через YooMoney API"""
    url = "https://yoomoney.ru/api/operation-history"
    
    headers = {
        "Authorization": f"Bearer {YOOMONEY_ACCESS_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "label": label
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    operations = result.get('operations', [])
                    
                    for operation in operations:
                        if operation.get('label') == label and operation.get('status') == 'success':
                            return True
                    
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        return False

# ==================== ОБРАБОТЧИКИ ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("📋 Мои покупки", callback_data="my_purchases")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton("💬 Поддержка", url="https://t.me/support")]
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"🎮 Добро пожаловать в <b>𝑺𝒉𝒊𝒏𝑹𝒐𝒌𝒂𝒚 VPN Bot</b>!\n\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"🔐 Мы предоставляем стабильные VPN конфигурации для игры в PUBG.\n\n"
        f"✨ Выберите действие из меню ниже:"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "buy_vpn":
        await show_tariffs(query)
    
    elif data == "my_purchases":
        await show_my_purchases(query, user_id)
    
    elif data == "info":
        await show_info(query)
    
    elif data == "admin_panel":
        if user_id in ADMIN_IDS:
            await show_admin_panel(query)
        else:
            await query.message.reply_text("❌ У вас нет доступа к админ панели.")
    
    elif data.startswith("buy_tariff_"):
        tariff_id = int(data.split("_")[2])
        await process_tariff_selection(query, user_id, tariff_id)
    
    elif data.startswith("check_payment_"):
        payment_id = data.split("_", 2)[2]
        await check_payment(query, user_id, payment_id)
    
    elif data == "admin_add_config":
        if user_id in ADMIN_IDS:
            await query.message.reply_text(
                "📁 Отправьте .conf файл для добавления в систему.\n"
                "Или отправьте /cancel для отмены."
            )
            context.user_data['awaiting_config'] = True
    
    elif data == "admin_stats":
        if user_id in ADMIN_IDS:
            await show_admin_stats(query)
    
    elif data == "admin_configs":
        if user_id in ADMIN_IDS:
            await show_admin_configs(query)
    
    elif data == "back_to_menu":
        await back_to_menu(query)

async def show_tariffs(query):
    """Показать тарифы"""
    tariffs = get_tariffs()
    available_configs = get_available_configs_count()
    
    if available_configs == 0:
        await query.message.edit_text(
            "❌ К сожалению, сейчас нет доступных конфигураций.\n"
            "Попробуйте позже или обратитесь в поддержку.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]])
        )
        return
    
    text = "🛒 <b>Выберите тариф:</b>\n\n"
    text += f"📦 Доступно конфигураций: <b>{available_configs}</b>\n\n"
    
    keyboard = []
    
    for tariff in tariffs:
        tariff_id, name, duration_days, price, description = tariff
        text += f"💎 <b>{name}</b> - {price} ₽\n"
        text += f"   {description}\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"💳 {name} - {price} ₽",
            callback_data=f"buy_tariff_{tariff_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def process_tariff_selection(query, user_id: int, tariff_id: int):
    """Обработка выбора тарифа"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, duration_days, price FROM tariffs WHERE id = ?", (tariff_id,))
    tariff = cursor.fetchone()
    conn.close()
    
    if not tariff:
        await query.message.edit_text("❌ Тариф не найден.")
        return
    
    name, duration_days, price = tariff
    
    # Проверяем наличие конфига
    config = get_available_config()
    if not config:
        await query.message.edit_text(
            "❌ К сожалению, конфигурации закончились.\n"
            "Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]])
        )
        return
    
    # Создаем платеж
    payment_id = create_payment(user_id, price)
    
    # Сохраняем данные о тарифе в context
    context_data = query._bot._application.user_data.get(user_id, {})
    context_data[f'payment_{payment_id}'] = {
        'tariff_id': tariff_id,
        'duration_days': duration_days,
        'price': price,
        'config_id': config[0]
    }
    query._bot._application.user_data[user_id] = context_data
    
    # Создаем ссылку на оплату
    payment_url = await create_yoomoney_payment(price, payment_id)
    
    text = (
        f"💳 <b>Оплата VPN</b>\n\n"
        f"📦 Тариф: <b>{name}</b>\n"
        f"💰 Сумма: <b>{price} ₽</b>\n"
        f"⏱ Срок: <b>{duration_days} дней</b>\n\n"
        f"🔗 Для оплаты перейдите по ссылке ниже:\n"
        f"После оплаты нажмите кнопку 'Проверить оплату'"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="buy_vpn")]
    ]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def check_payment(query, user_id: int, payment_id: str):
    """Проверка оплаты"""
    await query.answer("🔄 Проверяем оплату...")
    
    # Получаем данные о платеже
    context_data = query._bot._application.user_data.get(user_id, {})
    payment_data = context_data.get(f'payment_{payment_id}')
    
    if not payment_data:
        await query.message.edit_text("❌ Данные о платеже не найдены.")
        return
    
    # Проверяем статус платежа
    is_paid = await check_payment_status(payment_id)
    
    if is_paid:
        # Получаем конфиг
        config_id = payment_data['config_id']
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT config_name, config_data FROM vpn_configs WHERE id = ?", (config_id,))
        config = cursor.fetchone()
        conn.close()
        
        if not config:
            await query.message.edit_text("❌ Конфигурация не найдена.")
            return
        
        config_name, config_data = config
        
        # Сохраняем покупку
        add_purchase(
            user_id,
            config_id,
            payment_id,
            payment_data['price'],
            payment_data['duration_days']
        )
        
        # Помечаем конфиг как проданный
        mark_config_as_sold(config_id)
        
        # Обновляем статус платежа
        update_payment_status(payment_id, 'completed')
        
        # Отправляем конфиг пользователю
        success_text = (
            f"✅ <b>Оплата успешно подтверждена!</b>\n\n"
            f"🎉 Спасибо за покупку!\n"
            f"📁 Ваш VPN конфиг отправлен ниже.\n\n"
            f"📝 <b>Инструкция по подключению:</b>\n"
            f"1. Скачайте приложение WireGuard\n"
            f"2. Импортируйте полученный файл\n"
            f"3. Активируйте подключение\n\n"
            f"💬 Если возникнут вопросы - обращайтесь в поддержку!"
        )
        
        await query.message.edit_text(success_text, parse_mode='HTML')
        
        # Отправляем файл конфига
        from io import BytesIO
        config_file = BytesIO(config_data.encode('utf-8'))
        config_file.name = config_name
        
        await query.message.reply_document(
            document=config_file,
            filename=config_name,
            caption=f"📁 Ваш VPN конфиг: {config_name}"
        )
        
        # Уведомляем админов о продаже
        for admin_id in ADMIN_IDS:
            try:
                await query._bot.send_message(
                    admin_id,
                    f"💰 <b>Новая продажа!</b>\n\n"
                    f"👤 Пользователь: {query.from_user.first_name} (@{query.from_user.username})\n"
                    f"💵 Сумма: {payment_data['price']} ₽\n"
                    f"📁 Конфиг: {config_name}",
                    parse_mode='HTML'
                )
            except:
                pass
        
        # Очищаем данные о платеже
        del context_data[f'payment_{payment_id}']
        query._bot._application.user_data[user_id] = context_data
        
    else:
        await query.answer("❌ Оплата не найдена. Попробуйте еще раз через несколько секунд.", show_alert=True)

async def show_my_purchases(query, user_id: int):
    """Показать покупки пользователя"""
    purchases = get_user_purchases(user_id)
    
    if not purchases:
        text = "📋 У вас пока нет покупок."
    else:
        text = "📋 <b>Ваши покупки:</b>\n\n"
        
        for purchase in purchases:
            purchase_id, purchase_date, expiry_date, amount, config_name = purchase
            
            purchase_dt = datetime.fromisoformat(purchase_date)
            expiry_dt = datetime.fromisoformat(expiry_date)
            
            days_left = (expiry_dt - datetime.now()).days
            
            status = "✅ Активен" if days_left > 0 else "❌ Истек"
            
            text += (
                f"🔹 <b>{config_name}</b>\n"
                f"   💰 Сумма: {amount} ₽\n"
                f"   📅 Дата покупки: {purchase_dt.strftime('%d.%m.%Y')}\n"
                f"   ⏱ Истекает: {expiry_dt.strftime('%d.%m.%Y')}\n"
                f"   {status}"
            )
            
            if days_left > 0:
                text += f" ({days_left} дн.)\n\n"
            else:
                text += "\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_info(query):
    """Показать информацию"""
    text = (
        "ℹ️ <b>𝑺𝒉𝒊𝒏𝑹𝒐𝒌𝒂𝒚 VPN Bot</b>\n\n"
        "🎮 Специализированный VPN для игры в PUBG\n\n"
        "✨ <b>Преимущества:</b>\n"
        "• Низкий пинг\n"
        "• Стабильное соединение\n"
        "• Защита от блокировок\n"
        "• Автоматическая выдача\n"
        "• Техподдержка 24/7\n\n"
        "📱 <b>Поддерживаемые платформы:</b>\n"
        "• Android\n"
        "• iOS\n"
        "• Windows\n"
        "• macOS\n\n"
        "💬 По всем вопросам обращайтесь в поддержку!"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_panel(query):
    """Показать админ панель"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить конфиг", callback_data="admin_add_config")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 Конфиги", callback_data="admin_configs")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]
    
    text = "👨‍💼 <b>Админ панель</b>\n\nВыберите действие:"
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_stats(query):
    """Показать статистику"""
    stats = get_stats()
    
    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"📦 Доступно конфигов: <b>{stats['available_configs']}</b>\n"
        f"✅ Продано конфигов: <b>{stats['sold_configs']}</b>\n"
        f"💳 Всего покупок: <b>{stats['total_purchases']}</b>\n"
        f"💰 Общая выручка: <b>{stats['total_revenue']:.2f} ₽</b>\n"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def show_admin_configs(query):
    """Показать список конфигов"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT config_name, is_sold FROM vpn_configs ORDER BY added_date DESC LIMIT 20")
    configs = cursor.fetchall()
    conn.close()
    
    if not configs:
        text = "📁 Конфигов пока нет."
    else:
        text = "📁 <b>Последние 20 конфигов:</b>\n\n"
        
        for config_name, is_sold in configs:
            status = "❌ Продан" if is_sold else "✅ Доступен"
            text += f"• {config_name} - {status}\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загрузки документов"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    if not context.user_data.get('awaiting_config'):
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.conf'):
        await update.message.reply_text("❌ Пожалуйста, отправьте файл с расширением .conf")
        return
    
    # Скачиваем файл
    file = await context.bot.get_file(document.file_id)
    file_content = await file.download_as_bytearray()
    
    # Сохраняем в базу
    config_data = file_content.decode('utf-8')
    config_id = add_vpn_config(document.file_name, config_data)
    
    context.user_data['awaiting_config'] = False
    
    await update.message.reply_text(
        f"✅ Конфиг успешно добавлен!\n\n"
        f"📁 Имя файла: {document.file_name}\n"
        f"🆔 ID: {config_id}\n\n"
        f"Всего доступно: {get_available_configs_count()}"
    )

async def back_to_menu(query):
    """Вернуться в главное меню"""
    user = query.from_user
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("📋 Мои покупки", callback_data="my_purchases")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")],
        [InlineKeyboardButton("💬 Поддержка", url="https://t.me/support")]
    ]
    
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👨‍💼 Админ панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"🎮 <b>𝑺𝒉𝒊𝒏𝑹𝒐𝒌𝒂𝒚 VPN Bot</b>\n\n"
        f"✨ Выберите действие из меню:"
    )
    
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.")

# ==================== MAIN ====================
def main():
    """Главная функция"""
    # Инициализация БД
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
