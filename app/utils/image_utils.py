import logging
from typing import Optional, Dict

from app.config import IMAGE_SOURCE_PRIORITY, OPENAI_IMAGE_MODEL
from app.services import ai_service

logger = logging.getLogger(__name__)

async def get_final_image_url(
    news_item: Dict, 
    ai_generated_image_prompt: Optional[str]
) -> Optional[str]:
    """Определяет URL изображения для поста на основе настроек IMAGE_SOURCE_PRIORITY."""
    
    rss_image_url: Optional[str] = None
    # Извлечение URL изображения из RSS (аналогично тому, как это было раньше)
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

    ai_generated_image_url: Optional[str] = None

    async def _try_generate_ai_image() -> Optional[str]:
        nonlocal ai_generated_image_url
        if ai_generated_image_prompt and OPENAI_IMAGE_MODEL:
            logger.info(f"Попытка генерации AI изображения для новости: '{news_item.get('title', 'N/A')}' (промпт: {ai_generated_image_prompt[:100]}...)")
            ai_generated_image_url = await ai_service.generate_image_with_dalle(ai_generated_image_prompt)
            if ai_generated_image_url:
                logger.info("AI изображение успешно сгенерировано.")
                return ai_generated_image_url
            else:
                logger.warning("Не удалось сгенерировать AI изображение.")
        return None

    if IMAGE_SOURCE_PRIORITY == "none":
        logger.info("Постинг без изображения согласно настройке IMAGE_SOURCE_PRIORITY='none'.")
        return None

    if IMAGE_SOURCE_PRIORITY == "rss_only":
        if rss_image_url:
            logger.info(f"Используется изображение из RSS (rss_only): {rss_image_url}")
            return rss_image_url
        else:
            logger.info("Изображение из RSS не найдено (rss_only), постинг без изображения.")
            return None

    if IMAGE_SOURCE_PRIORITY == "ai_only":
        generated_url = await _try_generate_ai_image()
        if generated_url:
            logger.info(f"Используется AI изображение (ai_only): {generated_url}")
            return generated_url
        else:
            logger.info("AI изображение не сгенерировано (ai_only), постинг без изображения.")
            return None

    if IMAGE_SOURCE_PRIORITY == "rss_then_ai":
        if rss_image_url:
            logger.info(f"Используется изображение из RSS (rss_then_ai): {rss_image_url}")
            return rss_image_url
        logger.info("Изображение из RSS не найдено (rss_then_ai), попытка генерации AI изображения...")
        generated_url = await _try_generate_ai_image()
        if generated_url:
            logger.info(f"Используется AI изображение (rss_then_ai fallback): {generated_url}")
            return generated_url
        else:
            logger.info("AI изображение не сгенерировано (rss_then_ai fallback), постинг без изображения.")
            return None

    if IMAGE_SOURCE_PRIORITY == "ai_then_rss":
        generated_url = await _try_generate_ai_image()
        if generated_url:
            logger.info(f"Используется AI изображение (ai_then_rss): {generated_url}")
            return generated_url
        logger.info("AI изображение не сгенерировано (ai_then_rss), попытка использования изображения из RSS...")
        if rss_image_url:
            logger.info(f"Используется изображение из RSS (ai_then_rss fallback): {rss_image_url}")
            return rss_image_url
        else:
            logger.info("Изображение из RSS не найдено (ai_then_rss fallback), постинг без изображения.")
            return None
            
    # На случай если IMAGE_SOURCE_PRIORITY имеет какое-то другое значение (хотя это проверяется в config.py)
    logger.warning(f"Неизвестное значение IMAGE_SOURCE_PRIORITY: {IMAGE_SOURCE_PRIORITY}. Постинг без изображения.")
    return None 