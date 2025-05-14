import feedparser
import asyncio
import logging
from typing import List, Dict, Optional

from app.config import RSS_FEED_URL

logger = logging.getLogger(__name__)

async def fetch_feed_entries() -> List[Dict]:
    """Асинхронно загружает и парсит RSS-ленту.

    Returns:
        Список словарей, где каждый словарь представляет запись из ленты.
        Возвращает пустой список в случае ошибки.
    """
    if not RSS_FEED_URL:
        logger.error("URL RSS-ленты не указан в конфигурации.")
        return []
    
    logger.info(f"Загрузка RSS-ленты: {RSS_FEED_URL}")
    try:
        # feedparser не является асинхронным по умолчанию, выполняем в executor
        loop = asyncio.get_event_loop()
        parsed_feed = await loop.run_in_executor(None, feedparser.parse, RSS_FEED_URL)
        
        if parsed_feed.bozo:
            # bozo установлен в 1, если лента не корректно сформирована
            # Однако, feedparser все равно может попытаться ее распарсить
            # Залогируем ошибку, но продолжим, если есть записи
            logger.warning(f"RSS-лента может быть некорректно сформирована: {RSS_FEED_URL}, ошибка: {parsed_feed.bozo_exception}")

        if parsed_feed.entries:
            logger.info(f"Найдено {len(parsed_feed.entries)} записей в RSS-ленте.")
            # Пример структуры записи, которую мы можем использовать:
            # entry = {
            #     'title': entry.get('title'),
            #     'link': entry.get('link'),
            #     'summary': entry.get('summary'), # или 'description'
            #     'published': entry.get('published_parsed') # struct_time
            #     'content': entry.get('content', [{}])[0].get('value') # Для полного контента, если есть
            #     'image_url': entry.media_content[0]['url'] if hasattr(entry, 'media_content') and entry.media_content else None
            # }
            return parsed_feed.entries
        else:
            logger.warning(f"В RSS-ленте не найдено записей: {RSS_FEED_URL}")
            return []
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке или парсинге RSS-ленты {RSS_FEED_URL}: {e}")
        return []

async def get_latest_news(count: int = 1) -> List[Dict]:
    """Возвращает последние 'count' новостей из RSS-ленты.

    Args:
        count: Количество последних новостей для получения.

    Returns:
        Список словарей с данными новостей.
    """
    entries = await fetch_feed_entries()
    # Записи обычно идут от новых к старым, так что берем первые 'count'
    return entries[:count]

# Пример использования (для тестирования сервиса отдельно):
# if __name__ == '__main__':
#     async def test_fetch():
#         news_items = await get_latest_news(5)
#         if news_items:
#             for item in news_items:
#                 print(f"Title: {item.get('title')}")
#                 print(f"Link: {item.get('link')}")
#                 # Попробуем найти URL изображения
#                 image_url = None
#                 if hasattr(item, 'media_content') and item.media_content:
#                     image_url = item.media_content[0].get('url')
#                 elif hasattr(item, 'links'): # Иногда картинка в links с type="image/..."
#                     for link_info in item.links:
#                         if link_info.get('type', '').startswith('image'):
#                             image_url = link_info.get('href')
#                             break
#                 if image_url:
#                     print(f"Image URL: {image_url}")
#                 print("-----")
#         else:
#             print("Новости не найдены.")
#     asyncio.run(test_fetch()) 