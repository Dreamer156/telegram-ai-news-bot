import logging
from typing import Optional
import requests
import io
import html

from aiogram import Bot
from aiogram.types import InputFile, URLInputFile
from aiogram.exceptions import TelegramAPIError

from app.config import TELEGRAM_CHANNEL_ID

logger = logging.getLogger(__name__)

def is_url(string: str) -> bool:
    return string.startswith('http://') or string.startswith('https://')

async def post_to_channel(bot: Bot, text: str, image_url: Optional[str] = None, image_path: Optional[str] = None) -> bool:
    """Отправляет сообщение с изображением (если указано) в Telegram канал.

    Args:
        bot: Экземпляр aiogram Bot.
        text: Текст сообщения (HTML-разметка, готовая к отправке).
        image_url: URL изображения для отправки.
        image_path: Локальный путь к изображению для отправки.
                    Приоритетнее image_url, если указаны оба.

    Returns:
        True, если сообщение успешно отправлено, иначе False.
    """
    if not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID не настроен. Невозможно отправить сообщение.")
        return False

    # text is now assumed to be ready HTML, so no escaping here
    # escaped_text = html.escape(text) # <--- REMOVE THIS

    try:
        photo_to_send: Optional[InputFile] = None
        # Caption also uses the raw HTML text, truncated
        # escaped_caption = html.escape(text) # <--- REMOVE THIS
        # Ensure caption is not too long for Telegram (1024 chars)
        # A simple slice might break HTML tags. For now, we'll use a simple slice.
        # A more robust solution would parse HTML and truncate text content.
        caption_for_photo = text[:1024]

        if image_path:
            try:
                # Проверка на существование файла, если это локальный путь
                # Это должно быть сделано перед вызовом, но для надежности можно и здесь
                # import os; if not os.path.exists(image_path): logger.error(...); return False
                photo_to_send = image_path
                logger.info(f"Отправка сообщения с локальным изображением: {image_path} в канал {TELEGRAM_CHANNEL_ID}")
            except Exception as e: # Ловим потенциальные ошибки с путем, если он некорректен
                logger.error(f"Ошибка с локальным путем изображения '{image_path}': {e}", exc_info=True)
                # Попытка отправить только текст
                image_path = None # Сбрасываем, чтобы не пытаться отправить битое фото
                photo_to_send = None

        elif image_url:
            if is_url(image_url):
                # Для URLInputFile не нужна предварительная загрузка, aiogram сделает это.
                photo_to_send = URLInputFile(image_url)
                logger.info(f"Отправка сообщения с изображением по URL: {image_url} в канал {TELEGRAM_CHANNEL_ID}")
            else:
                # Если image_url не URL, возможно, это идентификатор файла Telegram (file_id)
                # или требует специальной обработки, которую здесь не предусматриваем.
                # В данном случае, будем трактовать как file_id.
                photo_to_send = image_url
                logger.info(f"Отправка сообщения с изображением по file_id: {image_url} в канал {TELEGRAM_CHANNEL_ID}")
        
        if photo_to_send:
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=photo_to_send,
                caption=caption_for_photo, # Use pre-formatted, truncated HTML
                parse_mode="HTML"
            )
        else:
            logger.info(f"Отправка текстового сообщения в канал {TELEGRAM_CHANNEL_ID}")
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=text, # Use pre-formatted HTML
                parse_mode="HTML",
                disable_web_page_preview=False # Можно сделать True, если превью ссылок не нужны
            )
        
        logger.info(f"Сообщение успешно отправлено в канал {TELEGRAM_CHANNEL_ID}.")
        return True

    except TelegramAPIError as e:
        logger.error(f"Telegram API ошибка при отправке сообщения в канал {TELEGRAM_CHANNEL_ID}: {e.message}", exc_info=True) # Используем e.message и exc_info
        # Здесь можно добавить более специфичную обработку ошибок, например, если бот заблокирован в канале
        # e.g., if "bot was blocked by the user" in str(e).lower(): ...
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети (requests) при попытке доступа к URL изображения {image_url}: {e}", exc_info=True) # Добавлено exc_info=True
        # Попытка отправить только текст, если изображение не удалось загрузить
        try:
            logger.warning(f"Попытка отправить только текстовое сообщение в канал {TELEGRAM_CHANNEL_ID} после ошибки с изображением.")
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=text, # Use pre-formatted HTML in fallback as well
                parse_mode="HTML",
                disable_web_page_preview=False
            )
            logger.info(f"Текстовое сообщение успешно отправлено в канал {TELEGRAM_CHANNEL_ID} после ошибки с изображением.")
            return True # Сообщение (текст) всё же отправлено
        except Exception as fallback_e:
            logger.error(f"Ошибка при отправке текстового сообщения (fallback) в канал {TELEGRAM_CHANNEL_ID}: {fallback_e}", exc_info=True) # Добавлено exc_info=True
            return False
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при отправке сообщения в канал {TELEGRAM_CHANNEL_ID}: {e}", exc_info=True) # Добавлено exc_info=True
        return False

# Для тестирования можно добавить:
# if __name__ == '__main__':
#     import asyncio
#     from app.config import BOT_TOKEN # Убедитесь, что BOT_TOKEN есть для теста
#     async def test_post():
#         if not BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
#             print("BOT_TOKEN или TELEGRAM_CHANNEL_ID не установлены. Тест невозможен.")
#             return
#         
#         test_bot = Bot(token=BOT_TOKEN)
#         sample_text = "<b>Тестовый пост!</b>\nЭто <i>демонстрация</i> работы сервиса.\n<a href=\"http://example.com\">Ссылка</a>"
#         # Замените на реальный URL картинки для теста
#         sample_image_url = "https://www.python.org/static/community_logos/python-logo-master-v3-TM.png"
#         
#         success = await post_to_channel(test_bot, sample_text, image_url=sample_image_url)
#         print(f"Отправка с URL изображением: {'Успешно' if success else 'Ошибка'}")

#         # Тест без изображения
#         # success_no_image = await post_to_channel(test_bot, "Тестовый пост без картинки.")
#         # print(f"Отправка без изображения: {'Успешно' if success_no_image else 'Ошибка'}")

#         # Тест с локальным файлом (создайте dummy.png или укажите существующий)
#         # with open("dummy.png", "wb") as f: # Создаем пустой png для теста
#         #     f.write(requests.get(sample_image_url).content) 
#         # success_local_image = await post_to_channel(test_bot, "Тест с локальной картинкой!", image_path="dummy.png")
#         # print(f"Отправка с локальным изображением: {'Успешно' if success_local_image else 'Ошибка'}")

#         await test_bot.session.close()
#     asyncio.run(test_post()) 