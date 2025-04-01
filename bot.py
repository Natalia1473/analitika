import os
import logging
import sqlite3
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('engagement.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS engagement (
            chat_id INTEGER,
            user_id INTEGER,
            user_name TEXT,
            message_count INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    conn.commit()
    conn.close()

def update_engagement(chat_id, user_id, user_name):
    conn = sqlite3.connect('engagement.db')
    cursor = conn.cursor()
    cursor.execute('SELECT message_count FROM engagement WHERE chat_id=? AND user_id=?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        message_count = row[0] + 1
        cursor.execute(
            'UPDATE engagement SET message_count=? WHERE chat_id=? AND user_id=?',
            (message_count, chat_id, user_id)
        )
    else:
        message_count = 1
        cursor.execute(
            'INSERT INTO engagement (chat_id, user_id, user_name, message_count) VALUES (?, ?, ?, ?)',
            (chat_id, user_id, user_name, message_count)
        )
    conn.commit()
    conn.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message and message.chat and message.chat.type in ["group", "supergroup"]:
        chat_id = message.chat.id
        user = message.from_user
        user_id = user.id
        user_name = user.full_name
        update_engagement(chat_id, user_id, user_name)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('engagement.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT chat_id, SUM(message_count) as total_messages, COUNT(*) as users FROM engagement GROUP BY chat_id'
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Нет данных для статистики.")
        return

    stats_text = "Статистика по чатам:\n"
    top_chat_id = None
    top_messages = 0
    for chat_id, total_messages, users in rows:
        stats_text += f"Чат: {chat_id} - Сообщений: {total_messages}, Пользователей: {users}\n"
        if total_messages > top_messages:
            top_messages = total_messages
            top_chat_id = chat_id

    stats_text += f"\nЛучший чат: {top_chat_id} с {top_messages} сообщениями."
    await update.message.reply_text(stats_text)

async def userstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    conn = sqlite3.connect('engagement.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT user_name, message_count FROM engagement WHERE chat_id=? ORDER BY message_count DESC',
        (chat_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Нет данных по пользователям в этом чате.")
        return

    stats_text = "Статистика по пользователям:\n"
    for user_name, message_count in rows:
        stats_text += f"{user_name}: {message_count} сообщений\n"
    await update.message.reply_text(stats_text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для отслеживания активности. Отправляй сообщения — я буду считать их.")

async def run_bot():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Не найден токен TELEGRAM_BOT_TOKEN")
        return

    bot_app = ApplicationBuilder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("stats", stats))
    bot_app.add_handler(CommandHandler("userstats", userstats))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Явная инициализация и запуск бота
    await bot_app.initialize()
    await bot_app.start()

    # Запуск polling в отдельной задаче
    polling_task = asyncio.create_task(bot_app.updater.start_polling())
    
    # Ожидаем, пока бот не завершится (idle)
    await bot_app.updater.idle()

    # После завершения polling корректно останавливаем бота
    polling_task.cancel()
    await bot_app.stop()
    await bot_app.shutdown()

async def run_webserver():
    async def handle_root(request):
        return web.Response(text="Bot is running")
    
    app_web = web.Application()
    app_web.router.add_get("/", handle_root)
    port = int(os.environ.get("PORT", 8000))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"HTTP сервер запущен на порту {port}")
    
    while True:
        await asyncio.sleep(3600)
