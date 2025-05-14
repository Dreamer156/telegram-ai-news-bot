import logging
import os # Добавлен os для работы с файлами
from collections import deque # Для FIFO очереди при ограничении файла
from aiogram import Bot

from app.services import rss_service, ai_service, telegram_service
from app.config import OPENAI_IMAGE_MODEL, POSTED_LINKS_FILE, MAX_POSTED_LINKS_IN_FILE
from app.utils.image_utils import get_final_image_url

logger = logging.getLogger(__name__)

# Используем deque для хранения ссылок в памяти, чтобы легко управлять размером FIFO
POSTED_NEWS_LINKS: deque[str] = deque(maxlen=MAX_POSTED_LINKS_IN_FILE) 

def load_posted_links():
    """Загружает ранее опубликованные ссылки из файла в память."""
    global POSTED_NEWS_LINKS
    if os.path.exists(POSTED_LINKS_FILE):
        try:
            with open(POSTED_LINKS_FILE, 'r', encoding='utf-8') as f:
                # Читаем все строки, удаляя переносы строк
                links_from_file = [line.strip() for line in f if line.strip()]
                # Загружаем в deque, он сам ограничит количество до maxlen
                POSTED_NEWS_LINKS = deque(links_from_file, maxlen=MAX_POSTED_LINKS_IN_FILE)
                logger.info(f"Загружено {len(POSTED_NEWS_LINKS)} ссылок из {POSTED_LINKS_FILE}.")
        except Exception as e:
            logger.error(f"Ошибка при загрузке ссылок из {POSTED_LINKS_FILE}: {e}", exc_info=True)
    else:
        logger.info(f"Файл {POSTED_LINKS_FILE} не найден. Начинаем с чистого списка опубликованных ссылок.")

def save_posted_link(link: str):
    """Добавляет ссылку в память и сохраняет текущий список (ограниченный) в файл."""
    global POSTED_NEWS_LINKS
    if link not in POSTED_NEWS_LINKS: # Добавляем, только если ее там нет (хотя deque сам справится с дублями при добавлении)
        POSTED_NEWS_LINKS.append(link) # deque сам удалит старый элемент, если maxlen достигнут
        try:
            # Перезаписываем файл текущим содержимым deque
            with open(POSTED_LINKS_FILE, 'w', encoding='utf-8') as f:
                for l_item in POSTED_NEWS_LINKS:
                    f.write(f"{l_item}\n")
            logger.debug(f"Ссылка {link} добавлена и список сохранен в {POSTED_LINKS_FILE}.")
        except Exception as e:
            logger.error(f"Ошибка при сохранении ссылки в {POSTED_LINKS_FILE}: {e}", exc_info=True)

# Загружаем ссылки один раз при инициализации модуля
load_posted_links()

async def process_and_post_news(bot: Bot, news_item: dict):
    """Обрабатывает одну новость и постит ее, если она новая."""
    title = news_item.get('title', "Без заголовка")
    link = news_item.get('link', "")
    summary = news_item.get('summary') or news_item.get('description', "")

    if not link: # Если нет ссылки, мы не можем отследить уникальность
        logger.warning(f"Новость \"{title}\" не имеет ссылки, пропускаем.")
        return

    if link in POSTED_NEWS_LINKS:
        logger.info(f"Новость \"{title}\" ({link}) уже была опубликована (проверено по файлу/памяти), пропускаем.")
        return

    logger.info(f"Получена новая новость для постинга: \"{title}\". ({link})")
    
    # Попытка извлечь полный контент, если есть
    content_detail = news_item.get('content')
    full_content = None
    if content_detail and isinstance(content_detail, list) and len(content_detail) > 0:
        full_content = content_detail[0].get('value')
    
    # Попытка извлечь URL изображения из RSS
    rss_image_url: str | None = None
    if hasattr(news_item, 'media_content') and news_item.media_content and isinstance(news_item.media_content, list):
        for media in news_item.media_content:
            if media.get('medium') == 'image' and media.get('url'):
                rss_image_url = media.get('url')
                break
    if not rss_image_url and hasattr(news_item, 'links'):
        for link_info in news_item.links:
            if link_info.get('type', '').startswith('image/') and link_info.get('href'):
                rss_image_url = link_info.href
                break
    if not rss_image_url and hasattr(news_item, 'enclosures'):
         for enclosure in news_item.enclosures:
            if enclosure.get('type', '').startswith('image/') and enclosure.get('href'):
                rss_image_url = enclosure.href
                break

    ai_result = await ai_service.reformat_news_for_channel(
        news_title=title,
        news_summary=summary,
        news_link=link,
        news_content=full_content
    )
    
    if not ai_result:
        logger.error(f"Не удалось обработать новость \"{title}\" с помощью AI. Пропускаем.")
        return
        
    formatted_text, image_prompt = ai_result
    # final_image_url_to_post = rss_image_url # <--- Старая логика

    # # Если картинки из RSS нет, ИЛИ если мы хотим всегда генерировать новую через DALL-E (можно сделать опционально)
    # # Сейчас: если нет из RSS, но есть промпт от AI и DALL-E настроен, генерируем.
    # if not final_image_url_to_post and image_prompt and OPENAI_IMAGE_MODEL:
    #     logger.info(f"Генерирую изображение для поста \"{title}\" (промпт: {image_prompt[:100]}...)")
    #     generated_dalle_url = await ai_service.generate_image_with_dalle(image_prompt)
    #     if generated_dalle_url:
    #         final_image_url_to_post = generated_dalle_url
    #         logger.info(f"Изображение для \"{title}\" сгенерировано.")
    #     else:
    #         logger.warning(f"Не удалось сгенерировать изображение для \"{title}\". Пост будет без картинки от DALL-E.")
    # elif rss_image_url:
    #      logger.info(f"Использую изображение из RSS-ленты для \"{title}\".")
    # else:
    #     logger.info(f"Изображение для поста \"{title}\" не найдено и не будет сгенерировано.")

    # Новая логика выбора изображения
    final_image_url_to_post = await get_final_image_url(news_item, image_prompt)

    logger.info(f"Публикую пост \"{title}\" в канал...")
    
    success = await telegram_service.post_to_channel(
        bot=bot, 
        text=formatted_text, 
        image_url=final_image_url_to_post
    )
    
    if success:
        logger.info(f"Пост \"{title}\" успешно опубликован в канале!")
        save_posted_link(link) # <--- Сохраняем ссылку после успешного поста
    else:
        logger.error(f"Не удалось опубликовать пост \"{title}\" в канале.")


async def scheduled_post_job(bot: Bot):
    """Задание, выполняемое планировщиком для постинга новостей."""
    # load_posted_links() # Можно и здесь, если нужна перезагрузка при каждом запуске задачи, но лучше при старте модуля
    logger.info("Запуск задачи по расписанию: проверка новых новостей...")
    
    # Мы можем получать несколько последних новостей и обрабатывать их все
    # Это полезно, если RSS-лента обновляется часто, а бот проверяет реже
    latest_news_items = await rss_service.get_latest_news(count=5) # Берем, например, 5 последних
    
    if not latest_news_items:
        logger.info("Планировщик: Свежие новости в RSS-ленте не найдены.")
        return

    # Новости в RSS обычно идут от новых к старым.
    # Чтобы постить в хронологическом порядке (старые сначала, если их несколько новых),
    # можно их развернуть. Но для постинга одной самой свежей это не нужно.
    # Если мы обрабатываем несколько, и хотим постить самую новую из пачки, то первая и так самая новая.
    # Если же мы хотим опубликовать все 5 (если они новые), то лучше их развернуть.
    # Для текущей задачи, мы будем обрабатывать каждую из 5 новостей,
    # и функция process_and_post_news сама проверит, была ли она уже опубликована.
    
    processed_count = 0
    for news_item in reversed(latest_news_items): # Обрабатываем от старых к новым из полученной пачки
        try:
            await process_and_post_news(bot, news_item)
            processed_count += 1
        except Exception as e:
            title_for_log = news_item.get('title', 'N/A')
            logger.error(f"Ошибка при обработке новости \"{title_for_log}\" в scheduled_post_job: {e}", exc_info=True)
    
    logger.info(f"Планировщик: завершил проверку новостей. Обработано {processed_count} элементов.") 