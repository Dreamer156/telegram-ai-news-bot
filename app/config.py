import os
from dotenv import load_dotenv
import logging # Добавим для логгирования в случае некорректного ADMIN_ID

# Импортируем новую функцию для загрузки списка лент
from app.utils.common import load_feeds

# Загружаем переменные окружения из файла .env
load_dotenv()

# --- BEGIN DIAGNOSTIC PRINT ---
print(f"[CONFIG_DEBUG] Attempting to load OPENROUTER_CHAT_MODEL. Value from os.getenv: {os.getenv('OPENROUTER_CHAT_MODEL')}")
# --- END DIAGNOSTIC PRINT ---

logger = logging.getLogger(__name__) # Инициализируем логгер для этого модуля

# Токен вашего Telegram бота
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID администратора бота (число)
ADMIN_ID_STR = os.getenv("ADMIN_ID")
ADMIN_ID = None
if ADMIN_ID_STR:
    try:
        ADMIN_ID = int(ADMIN_ID_STR)
    except ValueError:
        logger.error(f"Ошибка: ADMIN_ID ('{ADMIN_ID_STR}') не является валидным числовым ID. Админ-команды не будут доступны.")

# API ключ для OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# URL RSS-ленты (одиночный, для обратной совместимости или если используется только одна лента)
# @DEPRECATED: Используйте FEEDS для списка лент из feeds.txt
RSS_FEED_URL = os.getenv("RSS_FEED_URL") 

# Загружаем список RSS-лент из файла feeds.txt (по умолчанию)
FEEDS_FILE_PATH = "feeds.txt" # Можно сделать настраиваемым через os.getenv, если нужно
FEEDS = load_feeds(FEEDS_FILE_PATH)

# ID Telegram канала/группы для постинга
# Может быть как @channelname, так и числовой ID (например, -1001234567890 для супергрупп/каналов)
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
if TELEGRAM_CHANNEL_ID and not TELEGRAM_CHANNEL_ID.startswith('@') and not TELEGRAM_CHANNEL_ID.startswith('-'):
    try:
        TELEGRAM_CHANNEL_ID = int(TELEGRAM_CHANNEL_ID)
    except ValueError:
        print(f"Ошибка: TELEGRAM_CHANNEL_ID ('{TELEGRAM_CHANNEL_ID}') не является валидным числовым ID или именем канала.")
        # Можно здесь возбудить исключение или установить значение по умолчанию, если требуется строгая проверка
        TELEGRAM_CHANNEL_ID = None

# Настройки AI провайдера
# Возможные значения: "openai", "openrouter"
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()

# API ключ для OpenRouter (если используется)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# Модель чата для OpenRouter (например, "qwen/qwen3-32b:free")
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "qwen/qwen3-32b:free")
# (Опционально) URL вашего сайта для OpenRouter (для рейтинга)
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "")
# (Опционально) Название вашего сайта для OpenRouter (для рейтинга)
OPENROUTER_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "")

# (Опционально) Ключ для API провайдера изображений (например, Unsplash)
IMAGE_PROVIDER_API_KEY = os.getenv("IMAGE_PROVIDER_API_KEY")

# (Опционально) Модель OpenAI для генерации изображений (например, "dall-e-3")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")

# Включена ли генерация изображений AI, если из RSS не пришло или указан приоритет AI
# ("True", "true", "1" -> True, иначе False)
IMAGE_GENERATION_ENABLED_STR = os.getenv("IMAGE_GENERATION_ENABLED", "False")
IMAGE_GENERATION_ENABLED = IMAGE_GENERATION_ENABLED_STR.lower() in ["true", "1"]

# (Опционально) URL для HTTP/S прокси (например, "http://user:pass@host:port")
PROXY_URL = os.getenv("PROXY_URL")

# Проверки на наличие обязательных переменных
if not BOT_TOKEN:
    raise ValueError("Необходимо установить переменную окружения BOT_TOKEN")
if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise ValueError("Необходимо установить переменную окружения OPENAI_API_KEY для AI_PROVIDER='openai'")
elif AI_PROVIDER == "openrouter" and not OPENROUTER_API_KEY:
    raise ValueError("Необходимо установить переменную окружения OPENROUTER_API_KEY для AI_PROVIDER='openrouter'")
elif AI_PROVIDER not in ["openai", "openrouter"]:
    raise ValueError(f"Неизвестное значение для AI_PROVIDER: '{AI_PROVIDER}'. Допустимые значения: 'openai', 'openrouter'.")

# Проверка на наличие RSS-лент
if not FEEDS:
    # Если список FEEDS пуст, проверяем старую переменную RSS_FEED_URL для обратной совместимости
    if RSS_FEED_URL:
        logger.warning("Список RSS-лент в файле 'feeds.txt' пуст или файл не найден. Используется одиночная лента из RSS_FEED_URL.")
        FEEDS.append(RSS_FEED_URL)
    else:
        raise ValueError(f"Необходимо настроить RSS-ленты в файле '{FEEDS_FILE_PATH}' или указать RSS_FEED_URL в .env")
elif RSS_FEED_URL and RSS_FEED_URL not in FEEDS:
    # Если RSS_FEED_URL задан, но его нет в FEEDS (возможно, feeds.txt был изменен), добавим его для консистентности
    # или просто выведем предупреждение, что он будет проигнорирован в пользу feeds.txt
    logger.warning(f"RSS_FEED_URL ('{RSS_FEED_URL}') указан в .env, но также используется список лент из '{FEEDS_FILE_PATH}'. "
                     f"RSS_FEED_URL будет добавлен в общий список лент, если его там еще нет.")
    if RSS_FEED_URL not in FEEDS:
         FEEDS.append(RSS_FEED_URL) # Добавляем, чтобы не потерять, если пользователь ожидает его работу

# Интервал для автоматического постинга новостей (в минутах)
# Если не указан, по умолчанию, например, каждые 4 часа (240 минут)
# Вы можете установить его в .env файле как POSTING_INTERVAL_MINUTES=60 (для каждого часа)
POSTING_INTERVAL_MINUTES = int(os.getenv("POSTING_INTERVAL_MINUTES", 240))

# Приоритет источника изображений: rss_then_ai, ai_then_rss, rss_only, ai_only, none
# По умолчанию: rss_then_ai
IMAGE_SOURCE_PRIORITY = os.getenv("IMAGE_SOURCE_PRIORITY", "rss_then_ai").lower()
VALID_IMAGE_PRIORITIES = ["rss_then_ai", "ai_then_rss", "rss_only", "ai_only", "none"]
if IMAGE_SOURCE_PRIORITY not in VALID_IMAGE_PRIORITIES:
    logger.warning(f"Некорректное значение для IMAGE_SOURCE_PRIORITY: '{IMAGE_SOURCE_PRIORITY}'. Используется значение по умолчанию 'rss_then_ai'.")
    IMAGE_SOURCE_PRIORITY = "rss_then_ai"

# Файл для хранения ссылок на опубликованные посты
POSTED_LINKS_FILE = os.getenv("POSTED_LINKS_FILE", "posted_links.txt")
# Максимальное количество ссылок, хранимых в файле (для предотвращения его разрастания)
# Старые ссылки будут удаляться при превышении этого лимита (FIFO)
MAX_POSTED_LINKS_IN_FILE = int(os.getenv("MAX_POSTED_LINKS_IN_FILE", 500))

# Настройки логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", None) # По умолчанию None, если не задан (вывод только в консоль)
# Если LOG_FILE пустая строка, тоже считаем что не задан
if LOG_FILE == "":
    LOG_FILE = None

# Вы можете добавить здесь и другие настройки, если они понадобятся 