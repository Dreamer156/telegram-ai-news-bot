import feedparser
import asyncio
import logging
from typing import List, Dict, Any # Changed Optional to Any for entry
from app.config import FEEDS # Changed from RSS_FEED_URL to FEEDS
import time # Added for sorting by date
from datetime import datetime # Added for robust date parsing

logger = logging.getLogger(__name__)

def get_entry_published_datetime(entry: Dict[str, Any]) -> Optional[datetime]:
    """Safely retrieves and parses the publication date of an RSS entry."""
    published_parsed = entry.get('published_parsed')
    if published_parsed:
        try:
            return datetime.fromtimestamp(time.mktime(published_parsed))
        except Exception:
            pass # Invalid struct_time

    published_str = entry.get('published') or entry.get('updated')
    if published_str:
        try:
            # Try parsing with feedparser's own utility if available, or common formats
            # For simplicity, directly trying common datetime formats if feedparser hasn't parsed it
            # This part might need to be more robust if various date formats are common
            return datetime.strptime(published_str, "%a, %d %b %Y %H:%M:%S %z") # RFC 822
        except ValueError:
            try:
                return datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ") # ISO 8601
            except ValueError:
                logger.warning(f"Could not parse date string: {published_str} for entry {entry.get('title', 'N/A')}")
    return None


async def fetch_single_feed(feed_url: str, loop: asyncio.AbstractEventLoop) -> List[Dict[str, Any]]:
    """Асинхронно загружает и парсит одну RSS-ленту."""
    logger.info(f"Загрузка RSS-ленты: {feed_url}")
    try:
        parsed_feed = await asyncio.wait_for(
            loop.run_in_executor(None, feedparser.parse, feed_url), 
            timeout=30.0
        )
        
        if parsed_feed.bozo:
            logger.warning(
                f"RSS-лента может быть некорректно сформирована: {feed_url}, "
                f"ошибка: {parsed_feed.bozo_exception}"
            )

        if parsed_feed.entries:
            logger.info(f"Найдено {len(parsed_feed.entries)} записей в RSS-ленте: {feed_url}")
            # Add feed_url to each entry for context if needed later
            for entry in parsed_feed.entries:
                entry['feed_source_url'] = feed_url
            return parsed_feed.entries
        else:
            logger.warning(f"В RSS-ленте не найдено записей: {feed_url}")
            return []
            
    except asyncio.TimeoutError:
        logger.error(f"Тайм-аут при загрузке или парсинге RSS-ленты {feed_url}")
        return []
    except Exception as e:
        logger.error(f"Ошибка при загрузке или парсинге RSS-ленты {feed_url}: {e}", exc_info=True)
        return []

async def fetch_feed_entries() -> List[Dict[str, Any]]: # Changed return type
    """Асинхронно загружает и парсит RSS-ленты из списка FEEDS в конфигурации.
    Собранные записи сортируются по дате публикации (от новых к старым).

    Returns:
        Список словарей, где каждый словарь представляет запись из ленты.
        Возвращает пустой список в случае ошибки или отсутствия записей.
    """
    if not FEEDS:
        logger.error("Список RSS-лент (FEEDS) не указан или пуст в конфигурации.")
        return []
    
    loop = asyncio.get_event_loop()
    tasks = [fetch_single_feed(feed_url, loop) for feed_url in FEEDS]
    
    all_entries_lists = await asyncio.gather(*tasks)
    
    aggregated_entries: List[Dict[str, Any]] = [] # Ensure type for aggregated_entries
    for entry_list in all_entries_lists:
        aggregated_entries.extend(entry_list)
    
    if not aggregated_entries:
        logger.info("Новые записи не найдены ни в одной из RSS-лент.")
        return []

    # Сортировка всех записей по дате публикации (от новых к старым)
    # Используем 'published_parsed' (time.struct_time) или 'published' (str)
    aggregated_entries.sort(key=lambda x: get_entry_published_datetime(x) or datetime.min, reverse=True)
    
    logger.info(f"Всего собрано и отсортировано {len(aggregated_entries)} записей из {len(FEEDS)} лент.")
    return aggregated_entries

async def get_latest_news(count: int = 1) -> List[Dict[str, Any]]: # Changed return type
    """Возвращает последние 'count' новостей из всех RSS-лент, отсортированных по дате.

    Args:
        count: Количество последних новостей для получения.

    Returns:
        Список словарей с данными новостей.
    """
    entries = await fetch_feed_entries()
    # Записи уже отсортированы от новых к старым в fetch_feed_entries
    return entries[:count]

# Пример использования (для тестирования сервиса отдельно):
# if __name__ == '__main__':
#     async def test_fetch():
#         # Убедитесь, что у вас есть файл .env или конфигурация FEEDS для теста
#         # Например, можно временно добавить FEEDS = ["http://example.com/rss"] сюда
#         # или настроить app.config правильно
#         from app.config import load_config # Для загрузки .env если тестируем так
#         load_config() # Загружаем переменные, включая FEEDS
        
#         logger.addHandler(logging.StreamHandler()) # Чтобы видеть логи в консоли
#         logger.setLevel(logging.INFO)

#         news_items = await get_latest_news(10) # Запросим 10 новостей
#         if news_items:
#             for item in news_items:
#                 pub_date = get_entry_published_datetime(item)
#                 print(f"Title: {item.get('title')}")
#                 print(f"Link: {item.get('link')}")
#                 print(f"Published: {pub_date.strftime('%Y-%m-%d %H:%M:%S') if pub_date else 'N/A'}")
#                 print(f"Source Feed: {item.get('feed_source_url', 'N/A')}")
#                 # ... (остальная логика извлечения данных, если нужна)
#                 print("-----")
#         else:
#             print("Новости не найдены.")
#     asyncio.run(test_fetch()) 