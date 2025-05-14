import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Токен вашего Telegram бота
BOT_TOKEN = os.getenv("BOT_TOKEN")

# API ключ для OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# URL RSS-ленты
RSS_FEED_URL = os.getenv("RSS_FEED_URL")

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


# (Опционально) Ключ для API провайдера изображений (например, Unsplash)
IMAGE_PROVIDER_API_KEY = os.getenv("IMAGE_PROVIDER_API_KEY")

# (Опционально) Модель OpenAI для генерации изображений (например, "dall-e-3")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")


# Проверки на наличие обязательных переменных
if not BOT_TOKEN:
    raise ValueError("Необходимо установить переменную окружения BOT_TOKEN")
if not OPENAI_API_KEY:
    raise ValueError("Необходимо установить переменную окружения OPENAI_API_KEY")
if not RSS_FEED_URL:
    raise ValueError("Необходимо установить переменную окружения RSS_FEED_URL")
if not TELEGRAM_CHANNEL_ID:
    raise ValueError("Необходимо установить переменную окружения TELEGRAM_CHANNEL_ID")

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

# Вы можете добавить здесь и другие настройки, если они понадобятся 