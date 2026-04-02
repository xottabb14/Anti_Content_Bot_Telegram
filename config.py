# Токен вашего бота (получить у @BotFather)
BOT_TOKEN = "токен_бота_телеграм"

DEBUG = False
# Список запрещенных доменов в ссылках
BLOCKED_DOMAINS = [
    "instagram.com",
    "facebook.com",
    "instagram. com",
    "facebook. com",
    "instagram .com",
    "facebook .com",
    "instagram . com",
    "facebook . com",
]

# Список запрещенных расширений файлов
BLOCKED_EXTENSIONS = [
    ".epub", ".fb2", ".mobi", ".azw", ".azw3", ".djvu",
    ".lit", ".lrf", ".lrx", ".prc", ".chm", ".oeb",
    ".oebzip", ".tr", ".tcr", ".rb", ".pdb", ".fb3",".zip"
]

# Список приветственных сообщений для новых пользователей
# Используйте {name} для вставки имени пользователя
WELCOME_MESSAGES = [
    "Приветствуем тебя, {name}! ",
    "Привет, {name}! Читай <a href='https://t.me/testgroup/36221/36243'>правила</a>"]

# ID темы #general (нужно получить, если бот должен отправлять в конкретную тему)
# Если оставить None, бот будет отправлять в общий чат (не в тему)
GENERAL_TOPIC_ID = -1000000000000_1
REPORT_TOPIC_ID = "-1000000000000_25196"

# Включить/выключить приветствия
ENABLE_WELCOME = True

# Настройки капчи
# Добавить боту право Блокировать пользователей 
ENABLE_CAPTCHA = False
CAPTCHA_TIMEOUT = 300 #5 мин
CAPTCHA_MAX_ATTEMPTS = 3
CAPTCHA_LENGTH = 6
