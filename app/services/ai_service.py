import openai
import logging
from typing import Optional, Tuple
import requests # Added for OpenRouter
import json     # Added for OpenRouter
import asyncio  # Moved import to top
import httpx # Добавили httpx
import re # For HTML cleaning
import html # For HTML cleaning

from app.config import (
    OPENAI_API_KEY, 
    OPENAI_IMAGE_MODEL,
    AI_PROVIDER,
    OPENROUTER_API_KEY,
    OPENROUTER_CHAT_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_SITE_NAME,
    PROXY_URL
)

logger = logging.getLogger(__name__)

# --- HTML Sanitization for Telegram (based on user suggestion) ---
TG_ALLOWED_TAGS_SET = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'a', 'tg-spoiler'}

def clean_for_tg_html(raw_html: str) -> str:
    """
    Cleans an HTML string to be compliant with Telegram's supported HTML subset.
    - Converts <p> and <br> tags to newlines.
    - Removes <code> and <pre> tags entirely.
    - Removes other unsupported HTML tags, keeping their content (unwrapping).
    - Ensures <a> tags have an href and escapes it.
    - Keeps other allowed tags (<b>, <i>, etc.) and their content.
    """
    if not raw_html:
        return ""

    # 1. Replace <p> (and /p) with double newlines, <br> with single newline
    text = re.sub(r'</?p[^>]*>', '\n\n', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

    # 2. Remove <code> and <pre> tags entirely (as per user suggestion for simplicity)
    text = re.sub(r'</?(code|pre)[^>]*>', '', text, flags=re.IGNORECASE)

    # 3. Iteratively process tags to handle simple nesting and unwrap unsupported tags.
    tag_pattern = re.compile(r'<([a-zA-Z0-9_\-]+)([^>]*)>(.*?)</\1>', re.DOTALL | re.IGNORECASE)

    def tag_replacer(m):
        tag_name = m.group(1).lower()
        attributes_str = m.group(2)
        inner_content = m.group(3)

        if tag_name == 'a':
            href_match = re.search(r"href\s*=\s*(['\"])(.*?)\1", attributes_str, re.IGNORECASE)
            if href_match:
                url = html.escape(href_match.group(2), quote=True)
                # Recursively clean inner content of the <a> tag
                return f'<a href="{url}">{clean_for_tg_html(inner_content)}</a>'
            else:
                # <a> without href, unwrap (keep content, remove tag)
                return clean_for_tg_html(inner_content)
        elif tag_name in TG_ALLOWED_TAGS_SET:
            # For other allowed simple tags (<b>, <i>, <code>, <tg-spoiler>, etc.)
            # Telegram typically doesn't support attributes for these other than href for <a>.
            # Recursively clean inner content.
            # Map strong to b, em to i, etc. for canonical form if desired, or keep as is if AI uses them.
            canonical_map = {'strong': 'b', 'em': 'i', 'ins': 'u', 'strike': 's', 'del': 's'}
            actual_tag = canonical_map.get(tag_name, tag_name)
            return f'<{actual_tag}>{clean_for_tg_html(inner_content)}</{actual_tag}>'
        else:
            # Not an allowed tag, unwrap (keep content, remove tag)
            return clean_for_tg_html(inner_content)

    # Iteratively apply the tag replacer to handle some level of nesting
    # A fixed number of iterations is a heuristic.
    previous_text = text
    for _ in range(5): # Iterate a few times
        current_text = tag_pattern.sub(tag_replacer, previous_text)
        if current_text == previous_text:
            break
        previous_text = current_text
    text = previous_text

    # 4. Consolidate multiple newlines (max 2 for paragraph feel) and strip
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Инициализация http клиента с учетом прокси (если он задан)
proxies_config = {"http://": PROXY_URL, "https://": PROXY_URL} if PROXY_URL else None
if proxies_config:
    httpx_client = httpx.AsyncClient(proxies=proxies_config)
else:
    httpx_client = httpx.AsyncClient()

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

async def _reformat_news_openai(full_prompt: str, news_title: str) -> Optional[Tuple[str, str]]:
    if not OPENAI_API_KEY:
        logger.error("OpenAI API ключ не настроен для OpenAI провайдера.")
        return None
    logger.info("Отправка запроса к OpenAI API для реформатирования новости...")
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=httpx_client)
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — ИИ-ассистент, помогающий готовить посты для Telegram-канала. Форматируй ответ строго для Telegram HTML. Разрешенные теги: <b>, <i>, <u>, <s>, <a href=\"URL\">, <tg-spoiler>. НЕ ИСПОЛЬЗУЙ теги <p>, <br>, <code>, или <pre>. Вместо <p> или <br> используй один или два символа новой строки (\n) для разделения абзацев. Заголовок новости выдели тегом <b>. Промпт для изображения должен быть АБСОЛЮТНО ПОСЛЕДНЕЙ строкой и не должен содержать никакого HTML."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7,
            max_tokens=1500 # Increased max_tokens slightly
        )
        
        if not response.choices or not response.choices[0].message or not response.choices[0].message.content:
            logger.error(f"Получен пустой или некорректный ответ от OpenAI API для новости: {news_title}")
            return None

        ai_response_text = response.choices[0].message.content.strip()
        lines = ai_response_text.split('\n')
        
        image_prompt = f"Abstract representation of AI and news: {news_title}" # Default fallback
        main_html_content = ai_response_text # Assume all is content initially

        if len(lines) > 1:
            last_line = lines[-1].strip()
            # Check if the last line looks like a prompt and not part of HTML
            if len(last_line.split()) > 1 and not '<' in last_line and not '>' in last_line and any(c.isalpha() for c in last_line):
                potential_prompt_text = "\n".join(lines[:-1]).strip()
                # Further check if the text *before* the last line ends sanely (e.g., not mid-HTML tag)
                if potential_prompt_text and (potential_prompt_text.endswith(('.', '!', '?', '</code>', '</a>')) or not potential_prompt_text.endswith('>')) :
                    main_html_content = potential_prompt_text
                    image_prompt = last_line
                    logger.info("Промпт для изображения выделен из ответа OpenAI.")
                else:
                    logger.warning("Последняя строка похожа на промпт, но текст перед ней обрывается. Используется запасной промпт.")
            else:
                logger.warning("Не удалось четко выделить промпт для изображения из ответа OpenAI (возможно, он часть HTML или отсутствует), используется запасной.")
        else:
            logger.warning("Ответ OpenAI слишком короткий для выделения отдельного промпта, используется запасной.")

        formatted_text = clean_for_tg_html(main_html_content)
        logger.info("Новость успешно реформатирована OpenAI и очищена для Telegram HTML.")
        return formatted_text, image_prompt

    except openai.APIConnectionError as e:
        logger.error(f"Ошибка соединения с OpenAI API: {e}", exc_info=True)
        return None
    except openai.RateLimitError as e:
        logger.error(f"Превышен лимит запросов к OpenAI API: {e}", exc_info=True)
        return None
    except openai.APIStatusError as e:
        logger.error(f"Ошибка статуса OpenAI API (код {e.status_code}): {e.response}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при взаимодействии с OpenAI API для реформатирования: {e}", exc_info=True)
        return None

async def _reformat_news_openrouter(full_prompt: str, news_title: str) -> Optional[Tuple[str, str]]:
    if not OPENROUTER_API_KEY:
        logger.error("OpenRouter API ключ не настроен для OpenRouter провайдера.")
        return None
    if not OPENROUTER_CHAT_MODEL:
        logger.error("Модель чата для OpenRouter не настроена.")
        return None

    logger.info(f"Отправка запроса к OpenRouter API (модель: {OPENROUTER_CHAT_MODEL}) для реформатирования новости...")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL
    if OPENROUTER_SITE_NAME:
        headers["X-Title"] = OPENROUTER_SITE_NAME
        
    data = {
        "model": OPENROUTER_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "Ты — ИИ-ассистент, помогающий готовить посты для Telegram-канала. Форматируй ответ строго для Telegram HTML. Разрешенные теги: <b>, <i>, <u>, <s>, <a href=\"URL\">, <tg-spoiler>. НЕ ИСПОЛЬЗУЙ теги <p>, <br>, <code>, или <pre>. Вместо <p> или <br> используй один или два символа новой строки (\n) для разделения абзацев. Заголовок новости выдели тегом <b>. Промпт для изображения должен быть АБСОЛЮТНО ПОСЛЕДНЕЙ строкой и не должен содержать никакого HTML."},
            {"role": "user", "content": full_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1500 # Increased max_tokens slightly
    }

    try:
        loop = asyncio.get_event_loop()
        response_obj = await loop.run_in_executor(
            None, 
            lambda: requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(data),
                timeout=60
            )
        )
        response_obj.raise_for_status()
        response_data = response_obj.json()

        if not response_data.get('choices') or not response_data['choices'][0].get('message') or not response_data['choices'][0]['message'].get('content'):
            logger.error(f"Получен пустой или некорректный ответ от OpenRouter API для новости: {news_title}. Ответ: {response_data}")
            return None

        ai_response_text = response_data['choices'][0]['message']['content'].strip()
        lines = ai_response_text.split('\n')

        image_prompt = f"Abstract representation of AI and news: {news_title}" # Default fallback
        main_html_content = ai_response_text # Assume all is content initially

        if len(lines) > 1:
            last_line = lines[-1].strip()
            if len(last_line.split()) > 1 and not '<' in last_line and not '>' in last_line and any(c.isalpha() for c in last_line):
                potential_prompt_text = "\n".join(lines[:-1]).strip()
                if potential_prompt_text and (potential_prompt_text.endswith(('.', '!', '?', '</code>', '</a>')) or not potential_prompt_text.endswith('>')):
                    main_html_content = potential_prompt_text
                    image_prompt = last_line
                    logger.info("Промпт для изображения выделен из ответа OpenRouter.")
                else:
                    logger.warning("Последняя строка похожа на промпт, но текст перед ней обрывается. Используется запасной промпт для OpenRouter.")
            else:
                logger.warning("Не удалось четко выделить промпт для изображения из ответа OpenRouter, используется запасной.")
        else:
            logger.warning("Ответ OpenRouter слишком короткий для выделения отдельного промпта, используется запасной.")
            
        formatted_text = clean_for_tg_html(main_html_content)
        logger.info("Новость успешно реформатирована OpenRouter и очищена для Telegram HTML.")
        return formatted_text, image_prompt

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к OpenRouter API: {e}", exc_info=True)
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON ответа от OpenRouter: {e}. Ответ: {response_obj.text if 'response_obj' in locals() else 'N/A'}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при взаимодействии с OpenRouter API: {e}", exc_info=True)
        return None

async def reformat_news_for_channel(news_title: str, news_summary: str, news_link: str, news_content: Optional[str] = None) -> Optional[Tuple[str, str]]:
    prompt_parts = [
        f"Ты — редактор Telegram-канала на тему AI и промпт-инжиниринга. Твоя задача — подготовить пост на основе следующей новости.",
        f"Новость:",
        f"- Заголовок: {news_title}",
        f"- Краткое содержание: {news_summary}"
    ]
    if news_content:
        prompt_parts.append(f"- Полный текст (если нужно для контекста, используй кратко): {news_content[:1000]}...")
    
    prompt_parts.extend([
        f"- Ссылка на источник: {news_link}",
        f"Пожалуйста, сделай следующее (весь ответ, КРОМЕ ПОСЛЕДНЕЙ СТРОКИ с промптом для изображения, должен быть в формате HTML, строго для Telegram):",
        "1. Напиши привлекательный и информативный текст для поста. Используй подходящие по теме эмодзи.",
        "2. Формат HTML должен быть совместим с Telegram: разрешены только теги <b>, <i>, <u>, <s>, <a href=\"URL\">текст ссылки</a>, <tg-spoiler>. Заголовок новости выдели тегом <b>.",
        "3. НЕ ИСПОЛЬЗУЙ теги <p>, <br>, <code>, или <pre>. Вместо <p> или <br> используй один или два символа новой строки (\n) для разделения абзацев или смысловых блоков.",
        f"4. В конце основного текста (перед хештегами) добавь ссылку на источник в формате <a href=\"{news_link}\">Читать дальше</a>. Убедись, что ссылка {news_link} правильная и кликабельная.",
        "5. После ссылки на источник добавь 3-5 релевантных хештегов (если они подходят). Обычным текстом, без специальных тегов для хештегов.",
        "6. АБСОЛЮТНО ПОСЛЕДНЕЙ СТРОКОЙ (после всего HTML-контента и хештегов) предложи текстовый промпт (на английском языке) для генерации изображения к этому посту. Промпт должен быть ярким, описывающим суть новости или ключевую идею. Пример: 'Futuristic AI brain connected to a network, digital art'. НЕ ПИШИ НИЧЕГО КРОМЕ САМОГО ПРОМПТА для изображения на этой строке, и НЕ ИСПОЛЬЗУЙ HTML для этой строки промпта.",
        f"Стиль канала: экспертный, но увлекательный. Целевая аудитория: интересующиеся AI, разработчики, промпт-инженеры."
    ])
    full_prompt = "\n".join(prompt_parts)

    if AI_PROVIDER == "openai":
        return await _reformat_news_openai(full_prompt, news_title)
    elif AI_PROVIDER == "openrouter":
        return await _reformat_news_openrouter(full_prompt, news_title)
    else:
        logger.error(f"Неизвестный AI провайдер: {AI_PROVIDER}. Проверьте конфигурацию.")
        return None

async def generate_image_with_dalle(prompt: str) -> Optional[str]:
    if not openai.api_key or not OPENAI_IMAGE_MODEL:
        logger.error("OpenAI API ключ или модель для изображений не настроены.")
        return None

    logger.info(f"Запрос на генерацию изображения DALL-E с промптом: {prompt}")
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=httpx_client)
        response = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        if not response.data or not response.data[0].url:
            logger.error(f"Получен пустой или некорректный ответ от DALL-E API для промпта: {prompt}")
            return None
            
        image_url = response.data[0].url
        logger.info(f"Изображение успешно сгенерировано: {image_url}")
        return image_url
    except openai.APIConnectionError as e:
        logger.error(f"Ошибка соединения с DALL-E API: {e}", exc_info=True)
        return None
    except openai.RateLimitError as e:
        logger.error(f"Превышен лимит запросов к DALL-E API: {e}", exc_info=True)
        return None
    except openai.APIStatusError as e:
        logger.error(f"Ошибка статуса DALL-E API (код {e.status_code}): {e.response}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при генерации изображения DALL-E: {e}", exc_info=True)
        return None

async def close_httpx_client():
    await httpx_client.aclose()
    logger.info("Глобальный httpx клиент успешно закрыт.") 