import asyncio
import logging
import logging.config
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties # Для DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage # <--- Добавляем импорт MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import BOT_TOKEN, POSTING_INTERVAL_MINUTES, TELEGRAM_CHANNEL_ID, LOG_LEVEL, LOG_FILE, POSTED_LINKS_FILE
from app.handlers import user_commands # Пока что user_commands будет пустым или с базовым хендлером
# import app.handlers.scheduled_tasks as scheduled_tasks # Раскомментировать, если будут задачи по расписанию
from app.scheduler import scheduled_post_job # Импортируем нашу задачу
from app.services import telegram_service
from app.services.ai_service import close_httpx_client # Для закрытия клиента
from app.utils.common import load_posted_links, save_posted_link # Для инициализации файла ссылок

# Настройка логирования
log_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
        },
        'simple': {
            'format': '%(asctime)s - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': LOG_LEVEL,
            'stream': 'ext://sys.stdout'  # Explicitly set stream
        }
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO', # Общий уровень для root логгера
    },
    'loggers': {
        'app': { # Логгер для нашего приложения
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False, # Не передавать сообщения от 'app' в root логгер, если есть свой хендлер
        },
        'aiogram': {
            'handlers': ['console'],
            'level': 'INFO', # Можно поставить WARNING для уменьшения спама от aiogram
            'propagate': False,
        },
        'apscheduler': {
            'handlers': ['console'],
            'level': 'INFO', # или WARNING
            'propagate': False,
        }
    }
}

if LOG_FILE:
    log_config['handlers']['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'formatter': 'detailed',
        'filename': LOG_FILE,
        'maxBytes': 1024 * 1024 * 5,  # 5 MB
        'backupCount': 3,
        'level': LOG_LEVEL,
        'encoding': 'utf-8'  # Add UTF-8 encoding for file handler
    }
    log_config['root']['handlers'].append('file')
    if 'app' in log_config['loggers']:
        log_config['loggers']['app']['handlers'].append('file')
    if 'aiogram' in log_config['loggers']:
        log_config['loggers']['aiogram']['handlers'].append('file')
    if 'apscheduler' in log_config['loggers']:
        log_config['loggers']['apscheduler']['handlers'].append('file')

logging.config.dictConfig(log_config)
logger = logging.getLogger(__name__) # Логгер для этого модуля (bot.py)

# Убедимся, что файл для хранения ссылок существует
if not os.path.exists(POSTED_LINKS_FILE):
    save_posted_link(POSTED_LINKS_FILE, "# This file stores links to already posted news to avoid duplicates.")
    logger.info(f"Создан файл для хранения опубликованных ссылок: {POSTED_LINKS_FILE}")

async def on_startup(bot: Bot, scheduler: AsyncIOScheduler):
    logger.info("Бот запускается...")
    # Запускаем планировщик только если он еще не запущен
    if not scheduler.running:
        try:
            scheduler.start()
            logger.info("APScheduler успешно запущен.")
        except Exception as e: # Catch potential errors like "SchedulerAlreadRunningError" just in case
            logger.error(f"Ошибка при запуске APScheduler: {e}", exc_info=True)
            # Если планировщик уже запущен (например, в редких случаях двойного вызова),
            # это не критично, но логируем.
            if "SchedulerAlreadyRunningError" in str(e) and not scheduler.running:
                 logger.info("Попытка запуска уже запущенного APScheduler, но он не активен. Странно.")
            elif scheduler.running:
                 logger.info("APScheduler уже был запущен (возможно, ошибка была из-за этого).")

    if POSTING_INTERVAL_MINUTES > 0:
        logger.info(
            f"Интервал автопостинга настроен на {POSTING_INTERVAL_MINUTES} минут. "
            f"Используйте /start_autopost для активации."
        )
    else:
        logger.info(
            "Автоматический постинг по расписанию отключен (POSTING_INTERVAL_MINUTES <= 0 в .env). "
            "Используйте /start_autopost, если хотите запустить его с валидным интервалом (требуется перезапуск после изменения .env)."
        )
    # Здесь можно добавить другие действия при старте, например, отправку сообщения администратору
    # (если ADMIN_ID настроен)

async def on_shutdown(bot: Bot, scheduler: AsyncIOScheduler):
    logger.info("Бот останавливается...")
    if scheduler.running:
        scheduler.shutdown(wait=False) # wait=False чтобы не блокировать завершение, если есть активные задачи
        logger.info("APScheduler остановлен.")
    await close_httpx_client() # Закрываем HTTP клиент
    logger.info("Бот успешно остановлен.")

async def main():
    if not BOT_TOKEN:
        logger.critical("Токен бота (BOT_TOKEN) не найден в переменных окружения. Завершение работы.")
        return

    # Исправляем DeprecationWarning
    # Вместо parse_mode в конструкторе Bot, используем DefaultBotProperties
    default_bot_properties = DefaultBotProperties(parse_mode=ParseMode.HTML.value) # Используем HTML по умолчанию
    bot = Bot(token=BOT_TOKEN, default=default_bot_properties)
    
    storage = MemoryStorage() # <--- Инициализируем MemoryStorage
    dp = Dispatcher(storage=storage) # <--- Передаем storage в Dispatcher
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow") # Пример указания таймзоны

    # Передаем scheduler и bot в хендлеры через workflow_data
    # Это позволит получить к ним доступ в хендлерах через аргументы функции
    dp["scheduler"] = scheduler 
    # dp["bot"] = bot # bot и так доступен через message.bot или как аргумент хендлера

    dp.include_router(user_commands.router)

    # Регистрация функций startup и shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("Starting bot polling...")
    try:
        # Передаем данные в on_startup/on_shutdown через аргументы polling
        await dp.start_polling(bot, scheduler=scheduler) 
    finally:
        # Этот блок выполнится при завершении dp.start_polling (например, по Ctrl+C)
        # on_shutdown уже вызовется через dp.shutdown.register
        # Дополнительно можно убедиться, что http клиент закрыт, если это не произошло в on_shutdown
        # await close_httpx_client() # Это уже есть в on_shutdown
        logger.info("Polling завершен.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную (KeyboardInterrupt/SystemExit).") 