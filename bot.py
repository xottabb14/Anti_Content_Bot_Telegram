#pip3 install python-telegram-bot
import re
import random
import sys
import asyncio
import io
from urllib.parse import urlparse
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.constants import ParseMode
import config

# Импортируем PIL для создания капчи
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

DEBUG = config.DEBUG  # Включаем полную отладку

# Хранилище для капч (только для новых пользователей, которые проходят проверку)
captcha_storage = {}

# Хранилище для задач таймаута
timeout_tasks = {}

def log(message):
    """Вывод сообщения в консоль"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if DEBUG:
        print(f"[{timestamp}] {message}")
    sys.stdout.flush()

# Компилируем регулярное выражение для поиска ссылок
URL_PATTERN = re.compile(r'https?://[^\s]+|www.[^\s]+')

def generate_captcha_code():
    """Генерация случайного кода капчи из цифр"""
    code = ''.join([str(random.randint(0, 9)) for _ in range(config.CAPTCHA_LENGTH)])
    return code

def create_captcha_image(code: str) -> bytes:
    """Создание изображения капчи"""
    width = 300
    height = 120
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # Пытаемся загрузить шрифт
    try:
        font_paths = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:\\Windows\\Fonts\\Arial.ttf",
        ]
        font = None
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, 40)
                break
        if font is None:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()

    # Шум (точки)
    for _ in range(1000):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(0, 100), random.randint(0, 100), random.randint(0, 100)))

    # Случайные линии
    for _ in range(10):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(random.randint(0, 150), random.randint(0, 150), random.randint(0, 150)), width=2)

    # Рисуем текст
    x_offset = 20
    for i, char in enumerate(code):
        y_offset = random.randint(-5, 5)
        color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
        draw.text((x_offset + i * 45, 40 + y_offset), char, fill=color, font=font)

    # Размытие
    image = image.filter(ImageFilter.GaussianBlur(radius=0.5))

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes.getvalue()

def extract_domain(url: str) -> str:
    """Извлекает домен из URL"""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Убираем www
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain
    except:
        return ""

def contains_blocked_link(text: str) -> bool:
    """Проверяет наличие запрещенных ссылок или доменов в тексте"""
    if not text:
        return False
    log(f"🔎 Анализ текста: '{text[:100]}'")

    # Проверяем ссылки
    urls = URL_PATTERN.findall(text)

    if DEBUG:
        log(f"🔍 Проверка текста на запрещенные ссылки")
        log(f"🔗 Найденные URL: {urls}")

    for url in urls:
        domain = extract_domain(url)
        
        if DEBUG:
            log(f"🌐 Извлеченный домен: '{domain}'")
        
        # Проверяем каждый запрещенный домен
        for blocked_domain in config.BLOCKED_DOMAINS:
            if DEBUG:
                log(f"   Сравниваем с: '{blocked_domain}'")
            
            # Проверяем различные варианты совпадения
            if (domain == blocked_domain or 
                domain.endswith('.' + blocked_domain) or
                blocked_domain in domain):
                if DEBUG:
                    log(f"🚫 Найдена запрещенная ссылка: {url} (домен: {domain}, блокируется: {blocked_domain})")
                return True

    # Проверяем наличие запрещенных доменов в любом тексте (не только в ссылках)
    text_lower = text.lower()
    for blocked_domain in config.BLOCKED_DOMAINS:
        if blocked_domain.lower() in text_lower:
            if DEBUG:
                log(f"🚫 Найден запрещенный домен в тексте: '{blocked_domain}'")
            return True

    log(f"✅ Запрещенных доменов не найдено")
    return False

def has_blocked_extension(filename: str) -> bool:
    """Проверяет расширение файла"""
    if not filename:
        return False
    filename_lower = filename.lower()
    for ext in config.BLOCKED_EXTENSIONS:
        if filename_lower.endswith(ext):
            return True
    return False

async def kick_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, user_name: str):
    """Кик пользователя из чата"""
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)
        log(f"👢 Пользователь {user_name} (ID: {user_id}) кикнут из чата")
        return True
    except Exception as e:
        log(f"❌ Ошибка при кике пользователя {user_id}: {e}")
        return False

async def cancel_timeout(user_id: int):
    """Отмена таймаута для пользователя"""
    if user_id in timeout_tasks:
        timeout_tasks[user_id].cancel()
        del timeout_tasks[user_id]
        log(f"⏰ Таймаут для {user_id} отменен")

async def timeout_captcha(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, user_name: str, captcha_msg_id: int, text_msg_id: int):
    """Функция таймаута капчи"""
    await asyncio.sleep(config.CAPTCHA_TIMEOUT)
    if user_id in captcha_storage:
        log(f"⏰ Таймаут капчи для {user_id}")
        
        try:
            await context.bot.delete_message(chat_id, captcha_msg_id)
        except:
            pass
        
        try:
            await context.bot.delete_message(chat_id, text_msg_id)
        except:
            pass
        
        await kick_user(context, chat_id, user_id, user_name)
        del captcha_storage[user_id]
        
        if user_id in timeout_tasks:
            del timeout_tasks[user_id]

async def refresh_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление капчи"""
    if not getattr(config, 'ENABLE_CAPTCHA', False):
        return
    query = update.callback_query

    try:
        await query.answer()
    except:
        pass

    data = query.data
    log(f"🔄 Запрос на обновление капчи: {data}")

    if data.startswith("refresh_"):
        user_id = int(data.split("_")[1])
    else:
        user_id = query.from_user.id

    chat_id = query.message.chat_id

    if user_id not in captcha_storage:
        log(f"❌ Нет активной капчи для {user_id}")
        try:
            await query.edit_message_text("❌ Капча не найдена")
        except:
            pass
        return

    captcha_data = captcha_storage[user_id]

    new_code = generate_captcha_code()
    captcha_data["code"] = new_code
    captcha_data["attempts"] = 0

    log(f"🔄 Новый код для {user_id}: {new_code}")

    captcha_image = create_captcha_image(new_code)

    keyboard = [[InlineKeyboardButton("🔄 Обновить капчу", callback_data=f"refresh_{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=captcha_image,
                caption=f"🔢 Новый код! Введите {config.CAPTCHA_LENGTH} цифр с картинки: "
            ),
            reply_markup=reply_markup
        )
        log(f"✅ Капча обновлена для {user_id}")
    except Exception as e:
        log(f"❌ Ошибка при обновлении капчи: {e}")

async def send_welcome_message_by_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user):
    """Отправка приветствия"""
    if not getattr(config, 'ENABLE_WELCOME', True):
        log(f"ℹ Приветствие отключено в настройках")
        return
    if user.username:
        user_display = f"@{user.username}"
    elif user.first_name:
        user_display = user.first_name
        if user.last_name:
            user_display += f" {user.last_name}"
    else:
        user_display = f"User {user.id}"

    welcome_text = random.choice(config.WELCOME_MESSAGES)
    welcome_text = welcome_text.format(name=user_display)

    try:
        if getattr(config, 'GENERAL_TOPIC_ID', None):
            topic_id = config.GENERAL_TOPIC_ID
            if isinstance(topic_id, str) and '_' in topic_id:
                _, topic_id = topic_id.split('_')
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_text,
                message_thread_id=int(topic_id),
                parse_mode=ParseMode.HTML
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_text,
                parse_mode=ParseMode.HTML
            )
        log(f"📨 Приветствие для {user_display}")
    except Exception as e:
        log(f"❌ Ошибка приветствия: {e}")

async def send_captcha(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, message: Message):
    """Отправка капчи с картинкой"""
    log(f"📤 Отправка капчи для {user.id}")
    captcha_code = generate_captcha_code()
    captcha_image = create_captcha_image(captcha_code)

    keyboard = [[InlineKeyboardButton("🔄 Обновить капчу", callback_data=f"refresh_{user.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if user.username:
        user_display = f"@{user.username}"
    elif user.first_name:
        user_display = user.first_name
        if user.last_name:
            user_display += f" {user.last_name}"
    else:
        user_display = f"User {user.id}"

    captcha_text = (
        f"Привет-привет! Мы очень рады тебе, но давай для начала убедимся что ты не бот🫶\n\n"
        f"{user_display}, пожалуйста, введи циферки, которые ты видишь на картинке.\n"
        f"⏱ У вас есть {config.CAPTCHA_TIMEOUT} секунд."
    )

    try:
        text_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=captcha_text,
            parse_mode=ParseMode.HTML
        )
        
        captcha_msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=captcha_image,
            caption=f"🔢 Введите {config.CAPTCHA_LENGTH} цифр с картинки: ",
            reply_markup=reply_markup
        )
        
        captcha_storage[user.id] = {
            "code": captcha_code,
            "message_id": captcha_msg.message_id,
            "text_message_id": text_msg.message_id,
            "attempts": 0
        }
        
        log(f"✅ Капча отправлена для {user.id}. Код: {captcha_code}")
        
        task = asyncio.create_task(
            timeout_captcha(context, user.id, chat_id, user_display, captcha_msg.message_id, text_msg.message_id)
        )
        timeout_tasks[user.id] = task
        
    except Exception as e:
        log(f"❌ Ошибка капчи для {user.id}: {e}")

async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /report"""
    message = update.message
    if not message:
        return

    # Проверяем, есть ли ответ на сообщение
    if not message.reply_to_message:
        await message.reply_text("Для жалобы нужно ответить на сообщение, нарушающее правила.")
        return

    reply_msg = message.reply_to_message
    report_topic_config = getattr(config, 'REPORT_TOPIC_ID', None)

    if not report_topic_config:
        await message.reply_text("❌ Функция жалоб не настроена администратором.")
        return

    # Парсим REPORT_TOPIC_ID (формат "ChatID_TopicID")
    dest_chat_id = message.chat.id
    dest_topic_id = None
    
    if isinstance(report_topic_config, str) and '_' in report_topic_config:
        dest_chat_id, dest_topic_id = report_topic_config.split('_')
        dest_topic_id = int(dest_topic_id)
    elif isinstance(report_topic_config, int):
        dest_topic_id = report_topic_config
    else:
        dest_chat_id = report_topic_config

    # Формируем ссылку на сообщение
    original_chat_id = str(reply_msg.chat.id)
    if original_chat_id.startswith('-100'):
        original_chat_id = original_chat_id[4:]
    
    msg_link = f"https://t.me/c/{original_chat_id}/{reply_msg.message_id}"
    
    report_text = f"Жалоба на сообщение <a href=\"{msg_link}\">ID{reply_msg.message_id}</a>"
    
    try:
        # Отправляем текст жалобы в тему
        await context.bot.send_message(
            chat_id=dest_chat_id,
            message_thread_id=dest_topic_id,
            text=report_text,
            parse_mode=ParseMode.HTML
        )
        
        # Пересылаем само сообщение в тему
        await reply_msg.forward(
            chat_id=dest_chat_id,
            message_thread_id=dest_topic_id
        )
        
        # Отправляем подтверждение пользователю
        await message.reply_text("Ваша жалоба отправлена на рассмотрение")
        
        log(f"🚩 Жалоба от {message.from_user.username} на сообщение {reply_msg.message_id}")
        
        # Удаляем команду репорта (опционально, для чистоты)
        try:
            await message.delete()
        except:
            pass
            
    except Exception as e:
        log(f"❌ Ошибка отправки жалобы: {e}")
        await message.reply_text("❌ Произошла ошибка при отправке жалобы.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый обработчик всех сообщений"""
    message = update.effective_message
    if not message.chat.type in ["group", "supergroup"]:
        log(f"⏭ Не групповая беседа, игнорируем")
        return

    user_id = message.from_user.id

    # Логируем все сообщения для отладки
    log(f"📨 Получено сообщение от {message.from_user.username or message.from_user.first_name} (ID: {user_id})")
    if message.text:
        log(f"📝 Текст: {message.text[:200]}")
    if message.document:
        log(f"📎 Документ: {message.document.file_name}")
    if message.caption:
        log(f"📝 Подпись: {message.caption[:200]}")

    # ========== 1. СНАЧАЛА ПРОВЕРКА НА ЗАПРЕЩЕННЫЙ КОНТЕНТ ==========
    should_delete = False
    reason = ""

    # Проверяем текст сообщения
    if message.text:
        log(f"🔍 Проверяем текст на запрещенные ссылки...")
        if contains_blocked_link(message.text):
            should_delete = True
            reason = "ссылка в тексте"
            log(f"⚠ Найдена запрещенная ссылка в тексте!")

    # Проверяем подпись к медиа
    elif message.caption:
        log(f"🔍 Проверяем подпись на запрещенные ссылки...")
        if contains_blocked_link(message.caption):
            should_delete = True
            reason = "ссылка в подписи"
            log(f"⚠ Найдена запрещенная ссылка в подписи!")

    # Проверяем файлы
    if message.document and has_blocked_extension(message.document.file_name):
        should_delete = True
        reason = f"файл {message.document.file_name}"
        log(f"🚫 Найден запрещенный файл: {message.document.file_name}")
    elif message.audio and message.audio.file_name and has_blocked_extension(message.audio.file_name):
        should_delete = True
        reason = f"аудио {message.audio.file_name}"
        log(f"🚫 Найден запрещенный аудиофайл: {message.audio.file_name}")
    elif message.video and message.video.file_name and has_blocked_extension(message.video.file_name):
        should_delete = True
        reason = f"видео {message.video.file_name}"
        log(f"🚫 Найден запрещенный видеофайл: {message.video.file_name}")
    elif message.animation and message.animation.file_name and has_blocked_extension(message.animation.file_name):
        should_delete = True
        reason = f"анимация {message.animation.file_name}"
        log(f"🚫 Найден запрещенный файл анимации: {message.animation.file_name}")

    # Если найден запрещенный контент - удаляем и выходим
    if should_delete:
        try:
            await message.delete()
            log(f"✅ УДАЛЕНО сообщение от {message.from_user.username or message.from_user.first_name}: {reason}")
        except Exception as e:
            log(f"❌ Ошибка удаления: {e}")
        return

    # ========== 2. ПРОВЕРКА НА ВВОД КАПЧИ ==========
    if getattr(config, 'ENABLE_CAPTCHA', False) and user_id in captcha_storage and message.text:
        user_input = message.text.strip()
        captcha_data = captcha_storage[user_id]
        chat_id = message.chat.id
        
        log(f"🔍 Проверка ввода капчи от {user_id}: '{user_input}', правильный '{captcha_data['code']}'")
        
        try:
            await message.delete()
        except:
            pass
        
        if user_input == captcha_data["code"]:
            log(f"✅ Капча успешно пройдена для {user_id}")
            
            await cancel_timeout(user_id)
            
            try:
                await context.bot.delete_message(chat_id, captcha_data["message_id"])
            except:
                pass
            
            if "text_message_id" in captcha_data:
                try:
                    await context.bot.delete_message(chat_id, captcha_data["text_message_id"])
                except:
                    pass
            
            await send_welcome_message_by_user(context, chat_id, message.from_user)
            del captcha_storage[user_id]
            
        else:
            captcha_data["attempts"] += 1
            max_attempts = getattr(config, 'CAPTCHA_MAX_ATTEMPTS', 3)
            
            log(f"❌ Неправильный код. Попытка {captcha_data['attempts']}/{max_attempts}")
            
            if captcha_data["attempts"] >= max_attempts:
                log(f"💀 Превышено количество попыток для {user_id}")
                
                await cancel_timeout(user_id)
                
                try:
                    await context.bot.delete_message(chat_id, captcha_data["message_id"])
                except:
                    pass
                
                if "text_message_id" in captcha_data:
                    try:
                        await context.bot.delete_message(chat_id, captcha_data["text_message_id"])
                    except:
                        pass
                
                await kick_user(context, chat_id, user_id, message.from_user.username or message.from_user.first_name)
                del captcha_storage[user_id]
            else:
                remaining = max_attempts - captcha_data["attempts"]
                
                captcha_image = create_captcha_image(captcha_data["code"])
                
                keyboard = [[InlineKeyboardButton("🔄 Обновить капчу", callback_data=f"refresh_{user_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                try:
                    await context.bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=captcha_data["message_id"],
                        media=InputMediaPhoto(
                            media=captcha_image,
                            caption=f"❌ Неправильный код. Осталось попыток: {remaining}\n🔢 Введите {config.CAPTCHA_LENGTH} цифр с картинки: "
                        ),
                        reply_markup=reply_markup
                    )
                    log(f"🔄 Обновлено сообщение капчи для {user_id}")
                except Exception as e:
                    log(f"⚠ Не удалось обновить сообщение: {e}")
                    new_msg = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=captcha_image,
                        caption=f"❌ Неправильный код. Осталось попыток: {remaining}\n🔢 Введите {config.CAPTCHA_LENGTH} цифр с картинки: ",
                        reply_markup=reply_markup
                    )
                    captcha_data["message_id"] = new_msg.message_id
        
        return

    # ========== 3. ЕСЛИ ЗАПРЕЩЕННОГО КОНТЕНТА НЕТ И ЭТО НЕ ВВОД КАПЧИ ==========
    if getattr(config, 'ENABLE_CAPTCHA', False) and user_id in captcha_storage:
        log(f"⚠ Пользователь {user_id} проходит капчу, удаляем сообщение")
        try:
            await message.delete()
            log(f"🗑 Удалено сообщение от {user_id} (проходит капчу)")
        except Exception as e:
            log(f"❌ Ошибка удаления сообщения: {e}")
        return
    else:
        log(f"✅ Сообщение чистое и капча не требуется, оставляем")

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик новых участников"""
    message = update.effective_message
    log(f"🔍 Новый участник в {message.chat.title}")

    if not message.chat.type in ["group", "supergroup"]:
        return

    if message.new_chat_members:
        for new_member in message.new_chat_members:
            if new_member.id == context.bot.id:
                continue
            
            log(f"👤 Новый участник: {new_member.username or new_member.first_name} (ID: {new_member.id})")
            
            if getattr(config, 'ENABLE_CAPTCHA', False):
                await send_captcha(context, message.chat.id, new_member, message)
            else:
                await send_welcome_message_by_user(context, message.chat.id, new_member)

def main():
    """Запуск бота"""
    log("=" * 60)
    log("🚀 БОТ ЗАПУСКАЕТСЯ")
    log(f"📝 Капча: {'ВКЛ' if config.ENABLE_CAPTCHA else 'ВЫКЛ'}, длина: {config.CAPTCHA_LENGTH} цифр")
    log(f"⏱ Таймаут: {config.CAPTCHA_TIMEOUT} сек, попыток: {config.CAPTCHA_MAX_ATTEMPTS}")
    log(f"🚫 Удаление запрещенного контента: ВКЛ")
    log(f"🚫 Запрещенные домены: {', '.join(config.BLOCKED_DOMAINS)}")
    log(f"🚫 Запрещенные расширения: {', '.join(config.BLOCKED_EXTENSIONS[:5])}...")
    log("=" * 60)
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CallbackQueryHandler(refresh_captcha, pattern=r'^refresh_\d+$'))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    
    # Обработчик команды /report
    application.add_handler(CommandHandler("report", handle_report))

    # Единый обработчик для всех сообщений
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.Document.ALL | 
        filters.AUDIO | filters.VIDEO | filters.ANIMATION,
        handle_message
    ))

    log("✅ Бот готов")
    if config.ENABLE_CAPTCHA:
        log("⚠ ВАЖНО: Бот должен быть администратором группы с правами:")
        log("   - Удаление сообщений")
        log("   - Блокировка участников")
        log("ℹ СНАЧАЛА проверяется запрещенный контент, потом капча.")
        log("   Запрещенные ссылки и файлы удаляются у всех пользователей.")
        log("   Капча применяется ТОЛЬКО к новым пользователям.")
    else:
        log("ℹ Капча отключена. Бот только удаляет запрещенный контент.")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
