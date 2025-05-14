import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import BOT_TOKEN, POSTING_INTERVAL_MINUTES
from app.handlers import user_commands # Пока что user_commands будет пустым или с базовым хендлером
# import app.handlers.scheduled_tasks as scheduled_tasks # Раскомментировать, если будут задачи по расписанию
from app.scheduler import scheduled_post_job # Импортируем нашу задачу

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML) # Используем HTML разметку для красивых постов
    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(user_commands.router)

    # Настройка и запуск планировщика
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow") # Вы можете указать свой часовой пояс
    # Передаем экземпляр bot в нашу задачу, чтобы она могла его использовать
    scheduler.add_job(scheduled_post_job, 'interval', minutes=POSTING_INTERVAL_MINUTES, args=(bot,))
    scheduler.start()
    logger.info(f"Планировщик запущен с интервалом {POSTING_INTERVAL_MINUTES} минут.")

    logger.info("Starting bot polling...")
    
    # Удаляем вебхук, если он был установлен ранее, чтобы бот работал через polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        # Запускаем и бота, и позволяем планировщику работать в фоне
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()
        logger.info("Bot and scheduler stopped.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.") 