#pip3 install python-telegram-bot
import re
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

import config

# Компилируем регулярное выражение для поиска ссылок
URL_PATTERN = re.compile(r'https?://[^\s]+|www\.[^\s]+')

def extract_domain(url: str) -> str:
    """Извлекает домен из URL"""
    try:
        # Добавляем схему, если её нет
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
    """Проверяет наличие запрещенных ссылок в тексте"""
    if not text:
        return False

    urls = URL_PATTERN.findall(text)
    for url in urls:
        domain = extract_domain(url)
        for blocked_domain in config.BLOCKED_DOMAINS:
            if blocked_domain in domain or domain in blocked_domain:
                return True
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик входящих сообщений"""
    message = update.effective_message

    # Проверяем, что сообщение из группы
    if not message.chat.type in ["group", "supergroup"]:
        return

    # Флаг для удаления
    should_delete = False

    # Проверка ссылок в тексте сообщения
    if message.text and contains_blocked_link(message.text):
        should_delete = True

    # Проверка ссылок в подписи к медиа
    elif message.caption and contains_blocked_link(message.caption):
        should_delete = True

    # Проверка документов
    elif message.document and has_blocked_extension(message.document.file_name):
        should_delete = True

    # Проверка аудио файлов
    elif message.audio and message.audio.file_name and has_blocked_extension(message.audio.file_name):
        should_delete = True

    # Проверка видео файлов
    elif message.video and message.video.file_name and has_blocked_extension(message.video.file_name):
        should_delete = True

    # Проверка анимаций
    elif message.animation and message.animation.file_name and has_blocked_extension(message.animation.file_name):
        should_delete = True

    # Удаляем сообщение, если найдено нарушение
    if should_delete:
        try:
            await message.delete()
        except Exception:
            # Игнорируем ошибки при удалении
            pass

def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Добавляем обработчик сообщений
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.Document.ALL |
        filters.AUDIO | filters.VIDEO | filters.ANIMATION,
        handle_message
    ))

    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
