import logging
import html # для экранирования HTML символов в данных от пользователя, если нужно
import os # Добавлен os для работы с файлами
from datetime import datetime # Добавлена datetime для форматирования времени
# import re # Больше не нужен здесь, функция экранирования перенесена
import markdown # <--- Added import for the markdown library

from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ContentType
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.callback_data import CallbackData
# from aiogram.utils.formatting import Text, Markdown # <--- REMOVE Old import with incorrect Markdown
from aiogram.utils.formatting import Text # <--- Corrected import, Text might be used elsewhere

from apscheduler.schedulers.asyncio import AsyncIOScheduler # Для аннотации типа scheduler

from app.services import rss_service, ai_service, telegram_service
from app.config import (
    OPENAI_IMAGE_MODEL, ADMIN_ID, 
    RSS_FEED_URL, POSTING_INTERVAL_MINUTES, POSTED_LINKS_FILE,
    IMAGE_GENERATION_ENABLED, IMAGE_SOURCE_PRIORITY, # Добавлены для использования в post_latest_news
    TELEGRAM_CHANNEL_ID, AI_PROVIDER, OPENROUTER_CHAT_MODEL # Добавлены для cmd_status
)
from app.utils.image_utils import get_final_image_url # <--- Импортируем новую функцию
from app.utils.common import load_posted_links, markdown_v2_escape, save_posted_link # Используем функции из common.py

logger = logging.getLogger(__name__)
router = Router() # Создаем экземпляр Router

# --- FSM States for post preparation ---
class PreparePostStates(StatesGroup):
    awaiting_confirmation = State()

# --- CallbackData for post confirmation ---
class PostConfirmationCallback(CallbackData, prefix="post_confirm"):
    action: str # "publish" or "cancel"
    # We might add message_id or item_id later if needed for complex scenarios

# --- Клавиатура для администратора ---
admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/status"), KeyboardButton(text="/check_rss")],
        [KeyboardButton(text="/post_now"), KeyboardButton(text="/prepare_post")],
        [KeyboardButton(text="/start_autopost"), KeyboardButton(text="/stop_autopost")],
        [KeyboardButton(text="/help")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user_full_name_safe = markdown_v2_escape(message.from_user.full_name if message.from_user else "Пользователь")
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        text_part1 = markdown_v2_escape(f"Привет, {user_full_name_safe}! Я бот для постинга AI новостей.")
        text_part2 = markdown_v2_escape("Вы администратор. Используйте клавиатуру для управления.")
        full_text = f"{text_part1}\n{text_part2}"
        await message.answer(
            full_text,
            reply_markup=admin_keyboard,
            parse_mode=ParseMode.MARKDOWN_V2.value
        )
    else:
        full_text = markdown_v2_escape(f"Привет, {user_full_name_safe}! Я бот для постинга AI новостей.")
        await message.answer(
            full_text,
            parse_mode=ParseMode.MARKDOWN_V2.value
        )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    help_text_user = (
        f"{markdown_v2_escape('Я бот, который автоматически постит новости из RSS-лент на тему AI.')}\n\n"
        f"{markdown_v2_escape('Основные функции:')}\n"
        f"{markdown_v2_escape('- Автоматический постинг новостей из RSS.')}\n"
        f"{markdown_v2_escape('- Редактирование текста новости с помощью AI.')}\n"
        f"{markdown_v2_escape('- Добавление релевантного изображения к посту.')}"
    )
    help_text_admin = (
        f"\n\n{markdown_v2_escape('Команды администратора:')}\n"
        f"`/status` {markdown_v2_escape('- показать текущий статус и настройки бота.')}\n"
        f"`/check_rss` {markdown_v2_escape('- проверить RSS-ленту и показать последние 3 новости (без постинга).')}\n"
        f"`/post_now` {markdown_v2_escape('- немедленно запостить последнюю новость (если она еще не была опубликована).')}\n"
        f"`/prepare_post` {markdown_v2_escape('- подготовить новость, показать превью и запросить подтверждение перед постингом.')}\n"
        f"`/start_autopost` {markdown_v2_escape('- включить автоматический постинг новостей.')}\n"
        f"`/stop_autopost` {markdown_v2_escape('- выключить автоматический постинг новостей.')}\n"
        f"`/show_logs` {markdown_v2_escape('- показать последние логи (TODO).')}"
    )

    full_help_text = help_text_user
    if ADMIN_ID and message.from_user.id == ADMIN_ID:
        full_help_text += help_text_admin

    await message.reply(full_help_text, parse_mode=ParseMode.MARKDOWN_V2.value)

@router.message(Command("check_rss"))
async def cmd_check_rss(message: Message):
    """Обработчик команды /check_rss для проверки доступности RSS и количества новостей."""
    logger.info(f"Пользователь {message.from_user.id} вызвал /check_rss")
    if message.from_user.id != ADMIN_ID:
        await message.reply("Эта команда доступна только администратору.")
        return

    if not RSS_FEED_URL:
        await message.reply("URL RSS-ленты не настроен в .env файле.")
        return

    await message.reply("Проверка RSS-ленты... ⏳")
    try:
        # Используем существующий сервис для получения записей
        # feed_items = await rss_service.fetch_rss_feed(RSS_FEED_URL) # Получаем все новости из ленты
        feed_items = await rss_service.fetch_feed_entries() # Используем исправленную функцию
        if feed_items:
            await message.reply(f"✅ RSS-лента доступна ({RSS_FEED_URL}). Найдено новостей: {len(feed_items)}")
        else:
            await message.reply(f"RSS-лента ({RSS_FEED_URL}) доступна, но не содержит новостей или произошла ошибка при парсинге.")
    except Exception as e:
        logger.error(f"Ошибка при проверке RSS-ленты {RSS_FEED_URL}: {e}", exc_info=True)
        await message.reply(f"Произошла ошибка при проверке RSS: {e}")

@router.message(Command("post_now"))
async def cmd_post_now(message: Message, bot: Bot):
    """Обработчик команды /post_now. Принудительно постит последнюю новость."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /post_now от user_id: {message.from_user.id}")
        return

    logger.info(f"Администратор {message.from_user.id} инициировал команду /post_now")
    await telegram_service.post_latest_news(bot=bot, channel_id=TELEGRAM_CHANNEL_ID, posted_links_file=POSTED_LINKS_FILE)
    await message.reply(markdown_v2_escape("Попытка немедленного постинга инициирована. Смотрите логи для деталей."), parse_mode=ParseMode.MARKDOWN_V2.value)

@router.message(Command("status"))
async def cmd_status(message: Message, scheduler: AsyncIOScheduler, bot: Bot): # Добавили bot для DefaultBotProperties
    """Обработчик команды /status. Показывает статус бота и его настройки."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Попытка несанкционированного доступа к /status от user_id: {message.from_user.id}")
        return

    status_lines = [f"🤖 *Статус бота AI News Poster*:\n"]
    status_lines.append(f"*Состояние бота*: Активен ✅")
    
    # Проверка статуса автопостинга
    autopost_job = scheduler.get_job("scheduled_post_job")
    if autopost_job:
        status_lines.append(f"*Автопостинг*: `Включен` ✅")
        next_run_time = autopost_job.next_run_time
        if next_run_time:
            if next_run_time.tzinfo:
                next_run_local = next_run_time.astimezone()
                status_lines.append(f"  *Следующий пост*: `{next_run_local.strftime('%Y-%m-%d %H:%M:%S %Z')}`")
            else:
                status_lines.append(f"  *Следующий пост*: `{next_run_time.strftime('%Y-%m-%d %H:%M:%S')}` \(UTC\)")
    else:
        status_lines.append(f"*Автопостинг*: `Выключен` ❌")
        if POSTING_INTERVAL_MINUTES == 0:
            status_lines.append(markdown_v2_escape(f"  (Интервал в .env: {POSTING_INTERVAL_MINUTES} минут - автопост отключен в конфиге)"))
        else:
            status_lines.append(markdown_v2_escape(f"  (Интервал в .env: {POSTING_INTERVAL_MINUTES} минут)"))

    rss_feed_count = 1 if RSS_FEED_URL else 0
    status_lines.append(f"*Количество RSS\-лент*: `{rss_feed_count}`")
    status_lines.append(f"*Интервал автопостинга*: `{POSTING_INTERVAL_MINUTES} минут`")
    status_lines.append(f"*Канал для постинга*: `{markdown_v2_escape(str(TELEGRAM_CHANNEL_ID))}`")
    status_lines.append(f"*AI провайдер для текста*: `{markdown_v2_escape(AI_PROVIDER)}`")
    if AI_PROVIDER == "openrouter":
        status_lines.append(f"  *Модель OpenRouter*: `{markdown_v2_escape(OPENROUTER_CHAT_MODEL)}`")

    status_lines.append(f"*Генерация изображений*: `{'Включена' if IMAGE_GENERATION_ENABLED else 'Выключена'}`")
    if IMAGE_GENERATION_ENABLED:
        status_lines.append(f"  *Приоритет источника изображений*: `{markdown_v2_escape(str(IMAGE_SOURCE_PRIORITY))}`")
        status_lines.append(f"  *Модель OpenAI для изображений*: `{markdown_v2_escape(OPENAI_IMAGE_MODEL)}`")
    
    status_lines.append(f"*Файл с опубликованными ссылками*: `{markdown_v2_escape(POSTED_LINKS_FILE)}`")
    status_lines.append(markdown_v2_escape(f"*Текущий ParseMode бота (по умолчанию)*: `{bot.default.parse_mode if bot.default else 'Не установлен'}`"))

    try:
        next_run = scheduler.get_job("scheduled_post_job").next_run_time if scheduler.get_job("scheduled_post_job") else None
        if next_run:
            if next_run.tzinfo:
                next_run_local = next_run.astimezone()
                status_lines.append(f"*Следующий автоматический пост*: `{next_run_local.strftime('%Y-%m-%d %H:%M:%S %Z')}`")
            else:
                status_lines.append(f"*Следующий автоматический пост*: `{next_run.strftime('%Y-%m-%d %H:%M:%S')}` \(UTC\)")
        else:
            status_lines.append(f"*Следующий автоматический пост*: `Планировщик не активен или задача не найдена`")
    except Exception as e:
        logger.error(f"Ошибка при получении времени следующего запуска из APScheduler: {e}", exc_info=True)
        # status_lines.append(markdown_v2_escape(f"*Следующий автоматический пост*: `Ошибка получения данных ({str(e)})`"))
        # Строка выше заменена на блок автопостинга в начале функции
        pass # Ошибка уже нерелевантна если автопост не активен или инфо уже есть
        
    posted_links = load_posted_links(POSTED_LINKS_FILE)
    status_lines.append(f"*Количество уже опубликованных постов*: `{len(posted_links)}`")

    await message.reply("\n".join(status_lines), parse_mode=ParseMode.MARKDOWN_V2.value)

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

# --- Команды управления автопостингом ---
@router.message(Command("start_autopost"))
async def cmd_start_autopost(message: Message, scheduler: AsyncIOScheduler, bot: Bot):
    """Включает автоматический постинг новостей."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Несанкционированный доступ к /start_autopost от {message.from_user.id}")
        return

    if POSTING_INTERVAL_MINUTES is None or POSTING_INTERVAL_MINUTES <= 0:
        await message.reply(
            markdown_v2_escape("Автопостинг не может быть запущен. "
                               "Установите POSTING_INTERVAL_MINUTES > 0 в вашем .env файле и перезапустите бота."),
            parse_mode=ParseMode.MARKDOWN_V2.value
        )
        return

    job = scheduler.get_job("scheduled_post_job")
    if job:
        await message.reply(markdown_v2_escape("Автопостинг уже включен."), parse_mode=ParseMode.MARKDOWN_V2.value)
    else:
        scheduler.add_job(
            telegram_service.post_latest_news,
            'interval',
            minutes=POSTING_INTERVAL_MINUTES,
            args=[bot, TELEGRAM_CHANNEL_ID, POSTED_LINKS_FILE],
            id="scheduled_post_job",
            name="Scheduled News Posting",
            replace_existing=True
        )
        if not scheduler.running: # На случай если планировщик был остановлен как-то иначе
            scheduler.start()
            logger.info("Планировщик APScheduler запущен для автопостинга.")
        await message.reply(
            markdown_v2_escape(f"Автопостинг включен с интервалом {POSTING_INTERVAL_MINUTES} минут."),
            parse_mode=ParseMode.MARKDOWN_V2.value
        )
        logger.info(f"Автопостинг включен администратором {message.from_user.id} с интервалом {POSTING_INTERVAL_MINUTES} мин.")

@router.message(Command("stop_autopost"))
async def cmd_stop_autopost(message: Message, scheduler: AsyncIOScheduler):
    """Выключает автоматический постинг новостей."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Несанкционированный доступ к /stop_autopost от {message.from_user.id}")
        return

    job = scheduler.get_job("scheduled_post_job")
    if job:
        scheduler.remove_job("scheduled_post_job")
        await message.reply(markdown_v2_escape("Автопостинг выключен."), parse_mode=ParseMode.MARKDOWN_V2.value)
        logger.info(f"Автопостинг выключен администратором {message.from_user.id}")
    else:
        await message.reply(markdown_v2_escape("Автопостинг уже был выключен."), parse_mode=ParseMode.MARKDOWN_V2.value)

# --- Интерактивный постинг ---
@router.message(Command("prepare_post"))
async def cmd_prepare_post(message: Message, bot: Bot, state: FSMContext):
    """Готовит новость для постинга и показывает превью администратору."""
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        logger.warning(f"Несанкционированный доступ к /prepare_post от {message.from_user.id}")
        return
    
    await message.answer(markdown_v2_escape("Готовлю последнюю новость для превью... ⏳"), parse_mode=ParseMode.MARKDOWN_V2.value)

    try:
        # 1. Получаем последнюю новость (не опубликованную)
        latest_news_items = await rss_service.get_latest_news(count=1) # Используем count=1 для получения одной новости
        if not latest_news_items:
            await message.answer(markdown_v2_escape("Не удалось найти свежие новости в RSS-ленте для подготовки."), parse_mode=ParseMode.MARKDOWN_V2.value)
            return
        
        news_item = latest_news_items[0] # Берем первую (и единственную) новость
        title = news_item.get('title', "Без заголовка")
        link = news_item.get('link', "")
        summary = news_item.get('summary') or news_item.get('description', "")
        content_detail = news_item.get('content')
        full_content = None
        if content_detail and isinstance(content_detail, list) and len(content_detail) > 0:
            full_content = content_detail[0].get('value')

        # Проверяем, не был ли этот пост уже опубликован (на всякий случай, хотя get_latest_news должен это учитывать)
        posted_links = load_posted_links(POSTED_LINKS_FILE)
        if link and link in posted_links:
            await message.answer(markdown_v2_escape(f"Эта новость уже была опубликована: [{markdown_v2_escape(title)}]({link})"), parse_mode=ParseMode.MARKDOWN_V2.value)
            return

        # 2. Реформатируем с помощью AI
        ai_result = await ai_service.reformat_news_for_channel(
            news_title=title,
            news_summary=summary,
            news_link=link,
            news_content=full_content
        )
        if not ai_result:
            await message.answer(markdown_v2_escape("Не удалось обработать новость с помощью AI для превью."), parse_mode=ParseMode.MARKDOWN_V2.value)
            return
        
        formatted_text, image_prompt = ai_result

        # 3. Получаем URL изображения
        final_image_url_to_post = await get_final_image_url(news_item, image_prompt) # Передаем оригинальный news_item

        # 4. Сохраняем данные в FSM
        await state.set_state(PreparePostStates.awaiting_confirmation)
        await state.update_data(
            prepared_text=formatted_text, 
            prepared_image_url=final_image_url_to_post,
            news_link=link, # Сохраняем ссылку для отметки как опубликованной
            news_title=title # Для логов и сообщений
        )
        
        # 5. Отправляем превью администратору
        preview_prefix = "--- ПРЕВЬЮ ПОСТА ---\n\n" # Simple text prefix
        
        # Кнопки подтверждения
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=PostConfirmationCallback(action="publish").pack()),
                InlineKeyboardButton(text="❌ Отменить", callback_data=PostConfirmationCallback(action="cancel").pack())
            ]
            # TODO: Добавить кнопки "Редактировать AI" и "Новое изображение"
        ])

        if final_image_url_to_post:
            # Используем bot.send_photo, так как message.answer_photo нет, а message.reply_photo требует фото из файла/ID
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=final_image_url_to_post,
                caption=preview_prefix + formatted_text, # AI now provides HTML, prefix is plain
                parse_mode=ParseMode.HTML.value, # Use HTML for preview caption
                reply_markup=confirm_kb
            )
        else:
            await message.answer(
                preview_prefix + formatted_text, # AI now provides HTML, prefix is plain
                parse_mode=ParseMode.HTML.value, # Use HTML for preview message
                reply_markup=confirm_kb,
                disable_web_page_preview=False
            )
        await message.answer("Выберите действие для подготовленного поста.", parse_mode=None) # Plain text for this simple message

    except Exception as e:
        logger.error(f"Ошибка в /prepare_post: {e}", exc_info=True)
        await message.answer(markdown_v2_escape(f"Произошла ошибка при подготовке поста: {e}"), parse_mode=ParseMode.MARKDOWN_V2.value)
        await state.clear() # Очищаем состояние в случае ошибки


@router.callback_query(PostConfirmationCallback.filter(F.action == "publish"), StateFilter(PreparePostStates.awaiting_confirmation))
async def cq_publish_prepared_post(query: CallbackQuery, callback_data: PostConfirmationCallback, bot: Bot, state: FSMContext):
    user_data = await state.get_data()
    prepared_text = user_data.get("prepared_text")
    prepared_image_url = user_data.get("prepared_image_url")
    news_link = user_data.get("news_link")
    news_title = user_data.get("news_title", "Без заголовка")

    if not prepared_text:
        await query.answer("Ошибка: не найден текст для публикации. Попробуйте подготовить пост заново.", show_alert=True)
        await state.clear()
        await query.message.edit_reply_markup(reply_markup=None)
        return

    await query.answer("Публикую пост в канал...") # Ответ на нажатие кнопки

    success = await telegram_service.post_to_channel(
        bot=bot,
        text=prepared_text, # Pass HTML directly (it was stored as prepared_text from AI)
        image_url=prepared_image_url
    )

    await state.clear() # Clear state regardless of success, as the action is done.

    if success:
        if news_link:
            save_posted_link(POSTED_LINKS_FILE, news_link)
            logger.info(f"Опубликована новость '{news_title}' ({news_link}) через превью администратором {query.from_user.id}")
        else:
            logger.info(f"Опубликована новость '{news_title}' (без ссылки) через превью администратором {query.from_user.id}")
        
        post_title_snippet = news_title[:50]
        # Construct HTML confirmation message, escaping the dynamic title part
        confirmation_text = f'✅ Пост "<b>{html.escape(post_title_snippet)}</b>..." успешно опубликован в канале!'
        
        # Check content type of the original message to decide edit_text or edit_caption
        if query.message.content_type == ContentType.PHOTO:
            await query.message.edit_caption(
                caption=confirmation_text,
                reply_markup=None, # Remove buttons
                parse_mode=ParseMode.HTML.value
            )
        else: # Assuming it was a text message if not a photo
            await query.message.edit_text(
                text=confirmation_text, 
                reply_markup=None, # Remove buttons
                parse_mode=ParseMode.HTML.value
            )
    else:
        # Construct HTML error message, escaping the dynamic title part
        error_message_admin = f"❌ Ошибка при публикации поста '<b>{html.escape(news_title[:50])}</b>...' в канал. Детали в логах."
        if query.message.content_type == ContentType.PHOTO:
            await query.message.edit_caption(
                caption=error_message_admin,
                reply_markup=None, # Remove buttons
                parse_mode=ParseMode.HTML.value
            )
        else:
            await query.message.edit_text(
                text=error_message_admin, 
                reply_markup=None, # Remove buttons
                parse_mode=ParseMode.HTML.value
            )

@router.callback_query(PostConfirmationCallback.filter(F.action == "cancel"), StateFilter(PreparePostStates.awaiting_confirmation))
async def cq_cancel_prepared_post(query: CallbackQuery, callback_data: PostConfirmationCallback, state: FSMContext):
    user_data = await state.get_data()
    news_title = user_data.get("news_title", "Без заголовка")
    
    await query.answer("Публикация отменена.")
    await state.clear() # Clear state on cancellation

    # Construct HTML cancel message, escaping the dynamic title part
    cancel_text = f"❌ Публикация поста \"<b>{html.escape(news_title[:50])}</b>...\" отменена."
    
    if query.message.content_type == ContentType.PHOTO:
        await query.message.edit_caption(
            caption=cancel_text,
            reply_markup=None, # Remove buttons
            parse_mode=ParseMode.HTML.value
        )
    else:
        await query.message.edit_text(
            text=cancel_text, 
            reply_markup=None, # Remove buttons
            parse_mode=ParseMode.HTML.value
        )
    logger.info(f"Публикация новости '{news_title}' отменена администратором {query.from_user.id}")

# Не забыть зарегистрировать router в app/bot.py: dp.include_router(user_commands.router) 