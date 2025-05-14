import openai
import logging
from typing import Optional, Tuple
import requests # Added for OpenRouter
import json     # Added for OpenRouter
import asyncio  # Moved import to top
import httpx # Добавили httpx
import re # For HTML cleaning
import html # For HTML cleaning
from datetime import datetime # For build_messages
from bs4 import BeautifulSoup # For extracting excerpt from HTML

from app.config import (
    OPENAI_API_KEY, 
    OPENAI_IMAGE_MODEL,
    AI_PROVIDER,
    OPENROUTER_API_KEY,
    OPENROUTER_CHAT_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_SITE_NAME,
    PROXY_URL,
    OPENAI_CHAT_MODEL
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

# --- New Unified Prompt and Helper Functions ---

UNIFIED_PROMPT = \
"""
You are a professional Russian copy-writer for a Telegram channel
about AI and prompt-engineering.

== FORMAT (Telegram HTML only) ==
<b>🤖 {short_title}</b>

{teaser_paragraph (2-3 предложения, цепляющих читателя)}

{main_paragraph (что полезного, кто/зачем, без лишних деталей)}

{hashtags 3-5 штук вида #CamelCase}

== RULES ==
1. MAX 900 characters total (including tags and hashtags).
2. ONLY tags <b>, <i>, <u>, <s>. No other tags, no links.
3. Title ≤ 70 symbols, без точки в конце.
4. Если новости > 3 дней — добавь «[RETRO] » перед заголовком.
5. Пиши всегда на русском, даже если исходник другой.
"""

def build_messages(news_title: str, excerpt: str, publication_date: datetime, source_name: str) -> list[dict]:
    """Prepares the list of messages for the AI model based on the new unified prompt structure."""
    user_msg_content = f"""
Заголовок: {news_title}
Источник: {source_name}
Дата: {publication_date.strftime('%Y-%m-%d')}
Текст: {excerpt[:1200]}   # передаём не больше, чтобы не тратить токены
"""
    return [
        {"role": "system", "content": UNIFIED_PROMPT},
        {"role": "user",   "content": user_msg_msg_content.strip()},
    ]

def balance_specific_tag(text: str, tag_name: str) -> str:
    """Rudimentary balancing for a specific HTML tag (e.g., <b>, <i>).
    Ensures that if there are more open tags than close, missing close tags are appended.
    Does not handle complex nesting or incorrect ordering.
    """
    open_tag = f"<{tag_name}>"
    close_tag = f"</{tag_name}>"
    
    open_count = text.lower().count(open_tag.lower())
    close_count = text.lower().count(close_tag.lower())
    
    # Append missing closing tags
    if open_count > close_count:
        text += close_tag * (open_count - close_count)
    # Optional: Remove excess closing tags (more complex, for now focus on unclosed open tags)
    # elif close_count > open_count:
    #     pass # Or try to strip them, but could be risky
        
    return text

def sanitize_ai_response(text: str) -> str:
    """
    Sanitizes the AI's HTML output:
    - Removes forbidden <code> and <pre> tags.
    - Balances <b>, <i>, <u>, <s> tags.
    - Truncates to 900 characters as a final safety measure.
    """
    # Remove <code> and <pre> tags completely
    text = re.sub(r'</?(code|pre)(?:\s+[^>]*)?>', '', text, flags=re.IGNORECASE)

    # Balance allowed tags
    for tag in ['b', 'i', 'u', 's']:
        text = balance_specific_tag(text, tag)
        
    # Final truncation
    return text[:900]

async def _generate_post_from_llm(messages: list) -> str | None:
    """
    Internal function to generate post text from the LLM (OpenAI or OpenRouter).
    """
    ai_response_text = None
    try:
        if AI_PROVIDER == "openai":
            if not OPENAI_API_KEY:
                logger.error("OpenAI API key is not configured.")
                return None
            logger.info(f"Sending request to OpenAI model: {OPENAI_CHAT_MODEL}")
            
            # Using the openai library
            # Ensure you have the latest openai library installed and configured
            # For openai < 1.0
            # response = await asyncio.to_thread(
            #     openai.ChatCompletion.create,
            #     model=OPENAI_CHAT_MODEL,
            #     messages=messages,
            #     temperature=0.7, # Adjust as needed
            #     max_tokens=400  # Max output tokens
            # )
            # ai_response_text = response.choices[0].message['content'].strip()

            # For openai >= 1.0.0 (using a client, ideally initialized globally)
            # temp_openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY) # Should be global or passed
            # async with temp_openai_client as client:
            #     response = await client.chat.completions.create(
            #         model=OPENAI_CHAT_MODEL,
            #         messages=messages,
            #         temperature=0.7,
            #         max_tokens=400 
            #     )
            # ai_response_text = response.choices[0].message.content.strip()
            
            # Fallback to synchronous version if asyncio version causes issues with httpx_client structure
            # This is simpler to integrate with the existing httpx_client for OpenRouter
            # but ideally OpenAI calls would use its own async client.
            # For now, keeping it simple and similar to OpenRouter flow.
            
            payload = {
                "model": OPENAI_CHAT_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 400
            }
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            # Note: OpenAI's official Python client is preferred.
            # Using httpx here for consistency if the main client isn't fully async or for simplicity.
            # This assumes the OpenAI API endpoint structure.
            # It's better to use the official openai.AsyncOpenAI() client.
            # For now, this is a placeholder if we want to use httpx_client for everything.
            # It will likely require adjustment or using the official OpenAI library directly.
            #
            # Given the previous structure and user's code, let's assume a direct openai call is fine.
            # The user has `openai.api_key = OPENAI_API_KEY` at the top.
            # We'll use the older `openai.ChatCompletion.create` for now as it's simpler
            # with the existing top-level API key setup and doesn't require client management here.
            # If the user has openai >1.0, this will need to be updated.
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,  # Uses default ThreadPoolExecutor
                lambda: openai.ChatCompletion.create(
                    model=OPENAI_CHAT_MODEL,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=400
                )
            )
            ai_response_text = response.choices[0]['message']['content'].strip()


        elif AI_PROVIDER == "openrouter":
            if not OPENROUTER_API_KEY:
                logger.error("OpenRouter API key is not configured.")
                return None
            
            logger.info(f"Sending request to OpenRouter model: {OPENROUTER_CHAT_MODEL}")
            request_body = {
                "model": OPENROUTER_CHAT_MODEL,
                "messages": messages,
                "max_tokens": 350, # As per user's spec
                "temperature": 0.8, # As per user's spec
                # Add site URL and name if available and model supports it
                "site_url": OPENROUTER_SITE_URL, 
                "site_name": OPENROUTER_SITE_NAME,
            }
            # Filter out None values from request_body for site_url and site_name
            request_body = {k: v for k, v in request_body.items() if v is not None and v != ""}


            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": OPENROUTER_SITE_URL or "", 
                "X-Title": OPENROUTER_SITE_NAME or "",
                "Content-Type": "application/json"
            }
            
            response = await httpx_client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=request_body,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            if data.get("choices") and data["choices"][0].get("message"):
                ai_response_text = data["choices"][0]["message"]["content"].strip()
            else:
                logger.error(f"OpenRouter response missing expected content: {data}")
                return None
        else:
            logger.error(f"Unknown AI_PROVIDER: {AI_PROVIDER}")
            return None

        logger.info(f"AI response received successfully from {AI_PROVIDER}.")
        return ai_response_text

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling {AI_PROVIDER} API: {e.response.status_code} - {e.response.text}", exc_info=False)
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error calling {AI_PROVIDER} API: {e}", exc_info=False)
        return None
    except openai.error.OpenAIError as e: # Catch OpenAI specific errors
        logger.error(f"OpenAI API error: {e}", exc_info=False)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in _generate_post_from_llm with {AI_PROVIDER}: {e}", exc_info=True)
        return None

async def reformat_news_for_channel(
    news_title: str, 
    news_summary: str, # Kept for now, but excerpt from news_content is primary
    news_link: str, 
    news_content: str | None, # This is the full HTML from readability
    publication_date: datetime, 
    source_name: str
) -> tuple[str | None, str | None]:
    """
    Reformats a news item for the Telegram channel using the new unified prompt.
    Returns (formatted_text, image_prompt). Image prompt is currently always "SKIP".
    """
    logger.info(f"Reformatting news for channel: '{news_title[:50]}...' from {source_name}")

    excerpt = ""
    if news_content:
        try:
            soup = BeautifulSoup(news_content, 'html.parser')
            # Get text, join paragraphs with newlines, strip extra whitespace
            paragraphs = [p.get_text(strip=True) for p in soup.find_all(['p', 'div'])] # Basic extraction
            text_content = "\n\n".join(filter(None, paragraphs))
            if not text_content: # Fallback if no p/div or they are empty
                text_content = soup.get_text(separator='\n', strip=True)
            
            excerpt = text_content[:1200] # Truncate for the prompt
            logger.info(f"Extracted excerpt of {len(excerpt)} chars for AI.")
        except Exception as e:
            logger.error(f"Error parsing news_content with BeautifulSoup: {e}", exc_info=True)
            # Fallback to RSS summary if full content parsing fails
            excerpt = news_summary[:1200] if news_summary else ""
            logger.warning("Falling back to RSS summary for excerpt due to parsing error.")
    elif news_summary:
        excerpt = news_summary[:1200]
        logger.info("Using RSS summary as excerpt (no full content provided).")
    else:
        logger.warning("No news_content or news_summary available to create an excerpt for AI.")
        # If there's truly no content, AI might struggle. Title alone is not enough.
        return None, "SKIP" # Or handle as an error

    if not excerpt.strip(): # Ensure excerpt is not just whitespace
        logger.warning(f"Excerpt for '{news_title[:50]}...' is empty after processing. Cannot generate post.")
        return None, "SKIP"

    messages = build_messages(
        news_title=news_title,
        excerpt=excerpt,
        publication_date=publication_date,
        source_name=source_name
    )

    raw_ai_output = await _generate_post_from_llm(messages)

    if not raw_ai_output:
        logger.error(f"AI failed to generate content for: {news_title[:50]}...")
        return None, "SKIP"

    sanitized_html_post = sanitize_ai_response(raw_ai_output)
    
    logger.info(f"Successfully reformatted news: '{news_title[:50]}...'")
    # Image prompt is "SKIP" as per current strategy
    return sanitized_html_post, "SKIP" 

# (Optional) DALL-E image generation - can be kept if used elsewhere or removed
# For now, it's not called by the main reformat_news_for_channel flow.
async def generate_image_with_dalle(prompt: str) -> str | None:
    # ... (existing DALL-E code remains unchanged for now)
    if not OPENAI_API_KEY or not OPENAI_IMAGE_MODEL:
        logger.warning("OpenAI API key or DALL-E model not configured. Skipping image generation.")
        return None
    if prompt.strip().upper() == "SKIP":
        logger.info("Image prompt is 'SKIP', skipping DALL-E generation.")
        return None

    logger.info(f"Generating image with DALL-E, prompt: '{prompt[:100]}...'")
    try:
        # Using asyncio.to_thread for the blocking OpenAI call
        # For openai < 1.0
        # response = await asyncio.to_thread(
        #     openai.Image.create,
        #     prompt=prompt,
        #     n=1,
        #     size="1024x1024", # or "1792x1024" / "1024x1792" for DALL-E 3 if supported
        #     model=OPENAI_IMAGE_MODEL # Ensure this is dall-e-3 if using those sizes
        # )
        # image_url = response['data'][0]['url']
        
        # For openai >= 1.0.0 (using a client)
        # temp_openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        # async with temp_openai_client as client:
        #     response = await client.images.generate(
        #         model=OPENAI_IMAGE_MODEL,
        #         prompt=prompt,
        #         n=1,
        #         size="1024x1024" # DALL-E 3 supports "1024x1024", "1792x1024", or "1024x1792"
        #     )
        # image_url = response.data[0].url

        # Using the older openai.Image.create for simplicity with current API key setup
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: openai.Image.create(
                prompt=prompt,
                n=1,
                size="1024x1024",
                model=OPENAI_IMAGE_MODEL 
            )
        )
        image_url = response['data'][0]['url']

        logger.info(f"Image generated successfully: {image_url}")
        return image_url
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error during image generation: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during DALL-E image generation: {e}", exc_info=True)
        return None

async def close_httpx_client():
    """Closes the global httpx client."""
    if httpx_client and not httpx_client.is_closed:
        await httpx_client.aclose()
        logger.info("HTTPX client closed.")

# Remove old, unused constants and functions if they are fully replaced
# TG_ALLOWED_TAGS_SET - No longer needed as sanitize_ai_response handles allowed tags implicitly
# SYSTEM_PROMPT_NEWS_HTML - Replaced by UNIFIED_PROMPT
# clean_for_tg_html - Replaced by sanitize_ai_response

# Configure OpenAI API key if using OpenAI
if AI_PROVIDER == "openai" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    # For openai >= 1.0.0, client instantiation is preferred
    # openai_client = openai.OpenAI(api_key=OPENAI_API_KEY) # If using client

# Global httpx client for OpenRouter (and potentially OpenAI if we switch to httpx for it)
httpx_client = httpx.AsyncClient(proxies=PROXY_URL if PROXY_URL else None, timeout=60.0)

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