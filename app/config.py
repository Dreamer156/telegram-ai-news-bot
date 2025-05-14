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

# Вы можете добавить здесь и другие настройки, если они понадобятся 