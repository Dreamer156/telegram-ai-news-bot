import logging
import html # для экранирования HTML символов в данных от пользователя, если нужно
import os # Добавлен os для работы с файлами
from datetime import datetime # Добавлена datetime для форматирования времени

from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton # Добавлены ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.markdown import hbold, hlink, escape_md # Добавил escape_md

from app.services import rss_service, ai_service, telegram_service
from app.config import (
    OPENAI_IMAGE_MODEL, ADMIN_ID, 
    RSS_FEED_URLS, POSTING_INTERVAL_MINUTES, POSTED_LINKS_FILE,
    IMAGE_GENERATION_ENABLED, IMAGE_SOURCE_PRIORITY # Добавлены для использования в post_latest_news
)
from app.utils.image_utils import get_final_image_url # <--- Импортируем новую функцию
from app.scheduler import POSTED_NEWS_LINKS # Добавил для проверки опубликованных ссылок

logger = logging.getLogger(__name__)
router = Router() # Создаем экземпляр Router

# --- Клавиатура для администратора ---
admin_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="/post_latest_news"), KeyboardButton(text="/check_rss")],
    [KeyboardButton(text="/status")]
], resize_keyboard=True)

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /start от user_id: {message.from_user.id}")
        await message.reply("Этот бот доступен только администратору.", parse_mode=None)
        return
    await message.answer(f"Привет, {hbold(escape_md(message.from_user.full_name))}!\\nЯ бот для постинга AI-новостей. Используйте команды из меню ниже.", reply_markup=admin_kb)

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Обработчик команды /admin. Показывает админ-меню."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /admin от user_id: {message.from_user.id}")
        await message.reply("Эта команда доступна только администратору.", parse_mode=None)
        return
    await message.answer("Админ-меню:", reply_markup=admin_kb)

@router.message(Command("check_rss"))
async def cmd_check_rss(message: Message):
    """
    Обработчик команды /check_rss.
    Проверяет RSS-ленты и сообщает администратору о найденных новостях и их статусе публикации.
    """
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /check_rss от user_id: {message.from_user.id}")
        # Можно ничего не отвечать или ответить "Команда не найдена" для обычных пользователей
        # await message.reply("Эта команда доступна только администратору.", parse_mode=None)
        return

    await message.reply("Проверяю RSS-ленты, пожалуйста, подождите...", parse_mode=None)
    
    # Запрашиваем больше новостей, чтобы увидеть контекст
    latest_news_items = await rss_service.get_latest_news(count=10) 
    
    if not latest_news_items:
        await message.reply("Новых статей в RSS-лентах не обнаружено.", parse_mode=None)
        return

    response_lines = ["🔍 *Результаты проверки RSS-лент (до 10 последних)*:\n"]
    for i, item in enumerate(latest_news_items):
        title = item.get('title', "Без заголовка")
        link = item.get('link', "")
        source_feed = item.get('source_feed_url', 'Неизвестный источник')
        
        # Экранируем символы для MarkdownV2
        safe_title = escape_md(title)
        # Для ссылки hlink сам должензаботиться об экранировании URL, а текст нужно экранировать
        safe_link_display_text = escape_md(link if link else "Нет ссылки") 
        safe_source_feed = escape_md(source_feed)

        is_posted = "Да ✅" if link and link in POSTED_NEWS_LINKS else "Нет ❌"
        
        # Формируем строку с использованием hlink для ссылки
        # hlink(title, url) -> <a href="url">title</a> - это для HTML. Для MarkdownV2 нужно [text](url)
        # Поэтому делаем ссылку вручную, убедившись, что URL не содержит символов, которые сломают Markdown
        # (хотя URL обычно безопасны, но link может быть пустым)
        link_markdown = f"[{safe_link_display_text}]({link})" if link else safe_link_display_text

        line = (
            f"{i+1}\\. *{safe_title}*\n"
            f"   Источник: _{safe_source_feed}_\n"
            f"   Ссылка: {link_markdown}\n"
            f"   Уже опубликовано: {is_posted}\n"
        )
        response_lines.append(line)
    
    full_response = "\n".join(response_lines)
    
    # В Telegram есть ограничение на длину сообщения
    if len(full_response) > 4096:
        full_response = full_response[:4090] + "\\.\\.\\." # Обрезаем, если слишком длинно
        
    await message.reply(full_response, parse_mode="MarkdownV2", disable_web_page_preview=True)

@router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot): # Добавили bot для доступа к scheduler
    """Обработчик команды /status. Показывает статус бота и его настройки."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /status от user_id: {message.from_user.id}")
        return

    status_lines = [f"🤖 *Статус бота AI News Poster*:
"]
    status_lines.append(f"*Состояние бота*: Активен ✅")
    status_lines.append(f"*Количество RSS-лент*: `{len(RSS_FEED_URLS)}`")
    status_lines.append(f"*Интервал автопостинга*: `{POSTING_INTERVAL_MINUTES}` минут")
    status_lines.append(f"*Запомнено ссылок (в памяти)*: `{len(POSTED_NEWS_LINKS)}`")

    links_in_file_count = 0
    if POSTED_LINKS_FILE and os.path.exists(POSTED_LINKS_FILE):
        try:
            with open(POSTED_LINKS_FILE, 'r', encoding='utf-8') as f:
                links_in_file_count = sum(1 for _ in f)
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {POSTED_LINKS_FILE} для /status: {e}")
            links_in_file_count = "Ошибка чтения"
    status_lines.append(f"*Запомнено ссылок (в файле)*: `{links_in_file_count}`")

    # Получаем информацию о следующей задаче
    next_run_info = "Не удалось определить"
    try:
        # Пытаемся получить scheduler из объекта bot (если он был туда добавлен в main)
        # В aiogram 3, если dp["scheduler"] = scheduler, то он должен быть доступен так:
        scheduler = bot["scheduler"] # или message.bot["scheduler"]
        if scheduler:
            jobs = scheduler.get_jobs()
            if jobs:
                # Предполагаем, что у нас одна основная задача постинга
                # Можно улучшить, если задач несколько, искать по id
                next_run_time = jobs[0].next_run_time
                if next_run_time:
                    # Форматируем время, учитывая таймзону шедулера (если она есть)
                    # next_run_time уже должно быть aware datetime, если в шедулере есть таймзона
                    next_run_info = escape_md(next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z"))
                else:
                    next_run_info = "Задачи есть, но время следующего запуска не определено"
            else:
                next_run_info = "Запланированные задачи отсутствуют"
        else:
            next_run_info = "Экземпляр планировщика недоступен"
            logger.warning("Экземпляр планировщика не найден в bot context для команды /status")
    except KeyError:
        next_run_info = "Планировщик не найден в контексте бота (KeyError)."
        logger.warning("scheduler не найден в bot context по ключу 'scheduler' для команды /status")
    except Exception as e:
        logger.error(f"Ошибка при получении времени следующего запуска из APScheduler: {e}", exc_info=True)
        next_run_info = f"Ошибка получения ({escape_md(str(e))})"
        
    status_lines.append(f"*Следующий автопост*: `{next_run_info}`")

    await message.reply("\n".join(status_lines), parse_mode="MarkdownV2")

@router.message(Command("post_latest_news"))
async def cmd_post_latest_news(message: Message, bot: Bot):
    """Обработчик команды для постинга последней новости."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /post_latest_news от user_id: {message.from_user.id}")
        await message.reply("Эта команда доступна только администратору.", parse_mode=None)
        return

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
    # final_image_url_to_post = rss_image_url # <--- Старая логика

    # # Если картинки из RSS нет, ИЛИ если мы хотим всегда генерировать новую через DALL-E (можно сделать опционально)
    # # Сейчас: если нет из RSS, но есть промпт от AI и DALL-E настроен, генерируем.
    # if not final_image_url_to_post and image_prompt and OPENAI_IMAGE_MODEL:
    #     await message.answer(f"Генерирую изображение для поста (промпт: {image_prompt[:100]}...)")
    #     generated_dalle_url = await ai_service.generate_image_with_dalle(image_prompt)
    #     if generated_dalle_url:
    #         final_image_url_to_post = generated_dalle_url
    #         await message.answer("Изображение сгенерировано.")
    #     else:
    #         await message.answer("Не удалось сгенерировать изображение. Пост будет без картинки от DALL-E.")
    # elif rss_image_url:
    #      await message.answer("Использую изображение из RSS-ленты.")
    # else:
    #     await message.answer("Изображение для поста не найдено и не будет сгенерировано.")

    # Новая логика выбора изображения
    # В user_commands мы можем логировать в ответ пользователю, а не только в консоль
    await message.answer("Определяю изображение для поста согласно настройкам...")
    final_image_url_to_post = await get_final_image_url(news_item, image_prompt)

    if final_image_url_to_post:
        await message.answer(f"Изображение для поста определено: {final_image_url_to_post}")
    else:
        await message.answer("Пост будет опубликован без изображения.")

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