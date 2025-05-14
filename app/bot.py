import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from app.config import BOT_TOKEN
from app.handlers import user_commands # Пока что user_commands будет пустым или с базовым хендлером
# import app.handlers.scheduled_tasks as scheduled_tasks # Раскомментировать, если будут задачи по расписанию

# Настройка логирования
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML) # Используем HTML разметку для красивых постов
    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(user_commands.router)

    # Если будут задачи по расписанию, их нужно будет настроить и запустить отдельно
    # asyncio.create_task(scheduled_tasks.scheduler(bot)) # Пример

    logger.info("Starting bot...")
    
    # Удаляем вебхук, если он был установлен ранее, чтобы бот работал через polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.") 