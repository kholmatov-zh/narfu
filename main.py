import logging
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Простая in-memory "база" для пользователей
user_db = {}         # Формат: {user_id: {'fio': ..., 'group': ..., 'course': ...}}
user_state = {}      # Состояния регистрации: {user_id: "awaiting_fio"/"awaiting_group"/"awaiting_course"}
temp_registration = {}  # Временное хранилище данных регистрации

# Список администраторских ID (замените на актуальные)
ADMIN_IDS = [5159665027]

# Константы для ConversationHandler (админские команды)
BROADCAST, SEND_ID, SEND_TEXT = range(3)

# Словари для фото, ссылок и отображаемых названий для кнопок,
# требующих перехода на сайт
photo_paths = {
    "sakay": "photos/sakay.jpg",
    "mail": "photos/mail.jpg",
    "schedule": "photos/schedule.jpg",
    "interdept": "photos/interdept.jpg"
}

link_urls = {
    "sakay": "https://sakay.example.com",
    "mail": "https://mail.example.com",
    "schedule": "https://schedule.example.com",
    "interdept": "https://interdept.example.com"
}

display_names = {
    "sakay": "Сака́й",
    "mail": "Почта",
    "schedule": "Расписание",
    "interdept": "Межд Отдела"
}

# --------------------- Функции для обычных пользователей ---------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """При запуске проверяем регистрацию. Если пользователь не зарегистрирован – запускаем процесс регистрации."""
    user_id = update.effective_user.id
    if user_id not in user_db:
        user_state[user_id] = "awaiting_fio"
        temp_registration[user_id] = {}
        await update.message.reply_text("Добро пожаловать! Для регистрации введите ваше ФИО:")
    else:
        await update.message.reply_text("С возвращением!")
        await show_main_menu(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений во время регистрации."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = user_state.get(user_id)
    
    if state == "awaiting_fio":
        temp_registration[user_id]["fio"] = text
        user_state[user_id] = "awaiting_group"
        await update.message.reply_text("Введите номер группы (например, 123123):")
    elif state == "awaiting_group":
        temp_registration[user_id]["group"] = text
        user_state[user_id] = "awaiting_course"
        await update.message.reply_text("Введите курс (от 1 до 6):")
    elif state == "awaiting_course":
        if text.isdigit() and 1 <= int(text) <= 6:
            temp_registration[user_id]["course"] = int(text)
            # Сохраняем данные пользователя
            user_db[user_id] = {
                "fio": temp_registration[user_id]["fio"],
                "group": temp_registration[user_id]["group"],
                "course": temp_registration[user_id]["course"]
            }
            user_state[user_id] = None
            temp_registration.pop(user_id, None)
            await update.message.reply_text("Регистрация завершена!")
            await show_main_menu(update, context)
        else:
            await update.message.reply_text("Неверный ввод курса. Введите число от 1 до 6.")
    else:
        await update.message.reply_text("Пожалуйста, используйте главное меню или админские команды.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет главное меню с минималистичным оформлением и кнопками."""
    keyboard = [
        [InlineKeyboardButton("Профиль", callback_data="profile"),
         InlineKeyboardButton("Расписание", callback_data="schedule")],
        [InlineKeyboardButton("Почта", callback_data="mail"),
         InlineKeyboardButton("Корпуса", callback_data="campuses")],
        [InlineKeyboardButton("Медобследование", callback_data="medical"),
         InlineKeyboardButton("Техподдержка", callback_data="support")],
        [InlineKeyboardButton("Сака́й", callback_data="sakay")],
        [InlineKeyboardButton("Межд Отдела", callback_data="interdept")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text="Главное меню:", reply_markup=reply_markup)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок главного меню с удалением предыдущего сообщения и кнопкой 'Назад'."""
    query = update.callback_query
    await query.answer()  # Убираем "часики"
    data = query.data
    user_id = update.effective_user.id

    # Если нажата кнопка "Назад", возвращаемся в главное меню
    if data == "back":
        await query.message.delete()
        await show_main_menu(update, context)
        return

    # Удаляем предыдущее сообщение
    await query.message.delete()

    # Ключи, для которых нужна кнопка-ссылка (и кнопка "Назад")
    link_keys = {"sakay", "mail", "schedule", "interdept"}
    
    if data in link_keys:
        caption = f"{display_names[data]}: Чтобы перейти на сайт {display_names[data]}, нажмите кнопку 'Перейти'."
        photo_file = photo_paths.get(data)
        link_url = link_urls.get(data)
        keyboard = [
            [InlineKeyboardButton("Перейти", url=link_url)],
            [InlineKeyboardButton("Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            with open(photo_file, 'rb') as photo:
                await context.bot.send_photo(chat_id=user_id, photo=photo, caption=caption, reply_markup=reply_markup)
        except Exception as e:
            logging.error(f"Ошибка при отправке фото для {data}: {e}")
            await context.bot.send_message(chat_id=user_id, text=caption, reply_markup=reply_markup)
    else:
        # Обработка остальных пунктов: Профиль, Корпуса, Медобследование, Техподдержка
        if data == "profile":
            if user_id in user_db:
                profile = user_db[user_id]
                caption = (f"Ваш профиль:\nФИО: {profile['fio']}\n"
                           f"Группа: {profile['group']}\nКурс: {profile['course']}")
            else:
                caption = "Профиль не найден. Пожалуйста, зарегистрируйтесь."
            photo_file = "photos/profile.jpg"
        elif data == "campuses":
            caption = "Корпуса: Адреса и контакты корпусов вуза."
            photo_file = "photos/campuses.jpg"
        elif data == "medical":
            caption = "Медобследование: Информация о медосмотрах и дактилоскопии."
            photo_file = "photos/medical.jpg"
        elif data == "support":
            caption = "Техподдержка: Опишите вашу проблему, и мы свяжемся с вами."
            photo_file = "photos/support.jpg"
        else:
            await context.bot.send_message(chat_id=user_id, text="Неизвестная команда.")
            return
        
        keyboard = [[InlineKeyboardButton("Назад", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            with open(photo_file, 'rb') as photo:
                await context.bot.send_photo(chat_id=user_id, photo=photo, caption=caption, reply_markup=reply_markup)
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")
            await context.bot.send_message(chat_id=user_id, text=caption, reply_markup=reply_markup)

# --------------------- Административные функции ---------------------

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для массовой рассылки (только для админа)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для использования этой команды.")
        return ConversationHandler.END
    await update.message.reply_text("Введите текст объявления для рассылки:")
    return BROADCAST

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет объявление всем зарегистрированным пользователям."""
    text = update.message.text
    count = 0
    for uid in user_db.keys():
        try:
            await context.bot.send_message(chat_id=uid, text=f"Объявление:\n{text}")
            count += 1
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения пользователю {uid}: {e}")
    await update.message.reply_text(f"Рассылка завершена. Сообщение отправлено {count} пользователям.")
    return ConversationHandler.END

async def send_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для отправки личного сообщения конкретному студенту (админ)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для использования этой команды.")
        return ConversationHandler.END
    await update.message.reply_text("Введите Telegram ID студента:")
    return SEND_ID

async def send_message_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем Telegram ID студента и сохраняем его."""
    try:
        target_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Неверный формат ID. Попробуйте снова.")
        return SEND_ID
    context.user_data["target_id"] = target_id
    await update.message.reply_text("Введите текст сообщения для студента:")
    return SEND_TEXT

async def send_message_get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляем личное сообщение студенту по указанному ID."""
    target_id = context.user_data.get("target_id")
    text = update.message.text
    try:
        await context.bot.send_message(chat_id=target_id, text=f"Личное сообщение от администрации:\n{text}")
        await update.message.reply_text("Сообщение отправлено.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке сообщения: {e}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей команды."""
    await update.message.reply_text("Команда отменена.")
    return ConversationHandler.END

# --------------------- Функция для веб-сервера (uptime) ---------------------

PORT = 8080

async def run_webserver():
    """Запускает простой HTTP-сервер для пингов Uptime Robot."""
    app = web.Application()

    async def handle_ping(request):
        return web.Response(text="I'm alive!")

    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logging.info(f"Web-сервер запущен на порту {PORT}")

# --------------------- Основная функция ---------------------

def main():
    application = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    # Добавляем обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # ConversationHandler для массовой рассылки
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_command)],
        states={
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(broadcast_conv)
    
    # ConversationHandler для отправки личного сообщения студенту
    send_conv = ConversationHandler(
        entry_points=[CommandHandler("send_message", send_message_command)],
        states={
            SEND_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_message_get_id)],
            SEND_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_message_get_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(send_conv)
    
    # Создаем фоновую задачу для веб-сервера (uptime)
    asyncio.create_task(run_webserver())
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
