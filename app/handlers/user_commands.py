import logging
import html # для экранирования HTML символов в данных от пользователя, если нужно

from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold # Используем хелперы для HTML разметки

from app.services import rss_service, ai_service, telegram_service
from app.config import OPENAI_IMAGE_MODEL # Чтобы знать, используется ли DALL-E

logger = logging.getLogger(__name__)
router = Router() # Создаем экземпляр Router

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer(f"Привет, {hbold(message.from_user.full_name)}!\nЯ бот для постинга AI-новостей. Используйте команду /post_latest_news, чтобы опубликовать свежую новость.")

@router.message(Command("post_latest_news"))
async def cmd_post_latest_news(message: Message, bot: Bot):
    """Обработчик команды для постинга последней новости."""
    await message.answer("Получаю последнюю новость из RSS...")
    
    latest_news_items = await rss_service.get_latest_news(count=1)
    
    if not latest_news_items:
        await message.answer("Не удалось найти свежие новости в RSS-ленте. Попробуйте позже.")
        return

    news_item = latest_news_items[0]
    title = news_item.get('title', "Без заголовка")
    link = news_item.get('link', "")
    summary = news_item.get('summary') or news_item.get('description', "")
    
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
    if not rss_image_url and hasattr(news_item, 'links'): # Проверка в других полях
        for link_info in news_item.links:
            if link_info.get('type', '').startswith('image/') and link_info.get('href'):
                rss_image_url = link_info.href
                break
    if not rss_image_url and hasattr(news_item, 'enclosures'): # Иногда в enclosures
         for enclosure in news_item.enclosures:
            if enclosure.get('type', '').startswith('image/') and enclosure.get('href'):
                rss_image_url = enclosure.href
                break

    await message.answer(f"Новость получена: \"{title}\". Обрабатываю с помощью AI...")
    
    ai_result = await ai_service.reformat_news_for_channel(
        news_title=title,
        news_summary=summary,
        news_link=link,
        news_content=full_content
    )
    
    if not ai_result:
        await message.answer("Не удалось обработать новость с помощью AI. Попробуйте позже.")
        return
        
    formatted_text, image_prompt = ai_result
    final_image_url_to_post = rss_image_url # По умолчанию используем картинку из RSS, если есть

    # Если картинки из RSS нет, ИЛИ если мы хотим всегда генерировать новую через DALL-E (можно сделать опционально)
    # Сейчас: если нет из RSS, но есть промпт от AI и DALL-E настроен, генерируем.
    if not final_image_url_to_post and image_prompt and OPENAI_IMAGE_MODEL:
        await message.answer(f"Генерирую изображение для поста (промпт: {image_prompt[:100]}...)")
        generated_dalle_url = await ai_service.generate_image_with_dalle(image_prompt)
        if generated_dalle_url:
            final_image_url_to_post = generated_dalle_url
            await message.answer("Изображение сгенерировано.")
        else:
            await message.answer("Не удалось сгенерировать изображение. Пост будет без картинки от DALL-E.")
    elif rss_image_url:
         await message.answer("Использую изображение из RSS-ленты.")
    else:
        await message.answer("Изображение для поста не найдено и не будет сгенерировано.")

    await message.answer("Публикую пост в канал...")
    
    success = await telegram_service.post_to_channel(
        bot=bot, 
        text=formatted_text, 
        image_url=final_image_url_to_post
    )
    
    if success:
        await message.answer("Пост успешно опубликован в канале!")
    else:
        await message.answer("Не удалось опубликовать пост в канале. Проверьте логи и настройки.")

# Здесь можно добавить другие команды, например, для настройки RSS-ленты, стиля постов и т.д.
# Не забыть зарегистрировать router в app/bot.py: dp.include_router(user_commands.router) 