# Telegram AI News Poster Bot

Этот бот использует RSS-ленту для получения новостей на тему AI и промпт-инжиниринга.
Затем он обрабатывает текст новости с помощью API OpenAI (ChatGPT), форматирует его
в соответствии со стилем канала, добавляет релевантное изображение и публикует пост
в указанный Telegram-канал.

## Настройка

1.  **Клонируйте репозиторий (если это репозиторий):**
    ```bash
    git clone <your-repo-url>
    cd <project-folder>
    ```

2.  **Создайте и активируйте виртуальное окружение:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Для Linux/macOS
    # venv\Scripts\activate   # Для Windows
    ```

3.  **Установите зависимости:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Настройте переменные окружения:**
    *   Скопируйте файл `.env.example` в новый файл `.env`.
    *   Откройте `.env` и укажите ваши значения для следующих переменных:
        *   `BOT_TOKEN`: Ваш токен Telegram бота (полученный от @BotFather).
        *   `OPENAI_API_KEY`: Ваш API ключ для OpenAI.
        *   `RSS_FEED_URL`: URL RSS-ленты с новостями.
        *   `TELEGRAM_CHANNEL_ID`: ID вашего Telegram канала (например, `@yourchannelname` или числовой ID, например `-1001234567890`).
        *   `IMAGE_PROVIDER_API_KEY` (опционально): Если вы используете сторонний API для поиска изображений (например Unsplash).
        *   `OPENAI_IMAGE_MODEL` (опционально): Если вы планируете генерировать изображения через OpenAI DALL-E (например, `dall-e-3`).

## Запуск

```bash
python app/bot.py
```

## Структура проекта

```
/project_root
|-- /app
|   |-- __init__.py
|   |-- bot.py             # Главный файл запуска бота
|   |-- config.py          # Загрузка конфигурации
|   |-- /handlers
|   |   |-- __init__.py
|   |   |-- user_commands.py # Обработчики команд пользователя
|   |   |-- scheduled_tasks.py # (Опционально) Задачи по расписанию
|   |-- /services
|   |   |-- __init__.py
|   |   |-- rss_service.py   # Сервис для работы с RSS
|   |   |-- ai_service.py    # Сервис для взаимодействия с OpenAI API
|   |   |-- image_service.py # Сервис для поиска/генерации изображений
|   |   |-- telegram_service.py # Сервис для отправки сообщений в Telegram
|   |-- /utils
|   |   |-- __init__.py
|   |   |-- formatting.py    # Вспомогательные функции для форматирования
|   |-- /keyboards          # (Опционально) Модули для Telegram клавиатур
|       |-- __init__.py
|-- .env                 # Ваши секретные ключи (этот файл не должен быть в git)
|-- .env.example         # Пример файла с переменными окружения
|-- requirements.txt     # Зависимости проекта
|-- README.md            # Этот файл
``` 