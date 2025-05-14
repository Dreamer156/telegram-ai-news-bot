import openai
import logging
from typing import Optional, Tuple

from app.config import OPENAI_API_KEY, OPENAI_IMAGE_MODEL

logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logger.warning("OPENAI_API_KEY не найден. Функциональность AI будет недоступна.")

async def reformat_news_for_channel(news_title: str, news_summary: str, news_link: str, news_content: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Обращается к API OpenAI для реформатирования новости под стиль канала.

    Args:
        news_title: Заголовок новости.
        news_summary: Краткое содержание новости из RSS.
        news_link: Ссылка на оригинальную новость.
        news_content: Полное содержание новости, если доступно.

    Returns:
        Кортеж (formatted_text, image_prompt), где:
        - formatted_text: Отформатированный текст для поста в Telegram.
        - image_prompt: Промпт для генерации/поиска изображения.
        Или None в случае ошибки.
    """
    if not openai.api_key:
        logger.error("OpenAI API ключ не настроен.")
        return None

    # Составляем промпт для ChatGPT
    # Стиль канала: "AI новости и промпт-инжиниринг"
    # Задача: сделать пост привлекательным, информативным, добавить эмодзи, хештеги.
    
    prompt_parts = [
        f"Ты — редактор Telegram-канала на тему AI и промпт-инжиниринга. Твоя задача — подготовить пост на основе следующей новости.",
        f"Новость:",
        f"- Заголовок: {news_title}",
        f"- Краткое содержание: {news_summary}"
    ]
    if news_content:
        prompt_parts.append(f"- Полный текст (если нужно для контекста, используй кратко): {news_content[:1000]}...") # Ограничим длину полного текста
    
    prompt_parts.extend([
        f"- Ссылка на источник: {news_link}",
        f"Пожалуйста, сделай следующее:",
        "1. Напиши привлекательный и информативный текст для поста. Используй подходящие по теме эмодзи.",
        "2. Текст должен быть легко читаемым, возможно, разбит на абзацы.",
        "3. Включи в текст ссылку на источник новости.",
        "4. Придумай 3-5 релевантных хештегов (например, #AI #промптинжиниринг #новостиAI #технологии и т.д.).",
        "5. В конце, отдельной строкой, предложи текстовый промпт (на английском языке) для генерации изображения к этому посту с помощью нейросети (например, DALL-E). Промпт должен быть ярким, описывающим суть новости или ключевую идею. Пример: 'Futuristic AI brain connected to a network, digital art'. Не пиши ничего кроме самого промпта для изображения на этой строке."
        f"Стиль канала: экспертный, но увлекательный. Целевая аудитория: интересующиеся AI, разработчики, промпт-инженеры."
    ])
    
    full_prompt = "\n".join(prompt_parts)

    logger.info("Отправка запроса к OpenAI API для реформатирования новости...")
    try:
        # Используем новый клиент OpenAI v1.x.x+
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo", # или gpt-4, если доступен и предпочтителен
            messages=[
                {"role": "system", "content": "Ты — ИИ-ассистент, помогающий готовить посты для Telegram-канала."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.7, # Немного креативности
            max_tokens=1000 # Ограничение на длину ответа
        )
        
        if not response.choices or not response.choices[0].message or not response.choices[0].message.content:
            logger.error(f"Получен пустой или некорректный ответ от OpenAI API для новости: {news_title}")
            return None

        ai_response_text = response.choices[0].message.content.strip()
        
        # Разделяем текст поста и промпт для изображения
        # Предполагаем, что промпт для изображения будет на последней строке
        lines = ai_response_text.split('\n')
        if len(lines) > 1:
            image_prompt_candidate = lines[-1]
            # Простая проверка, что это может быть промпт (обычно на английском, содержит слова)
            if len(image_prompt_candidate.split()) > 2 and any(c.isalpha() for c in image_prompt_candidate):
                formatted_text = "\n".join(lines[:-1]).strip()
                image_prompt = image_prompt_candidate.strip()
                logger.info("Новость успешно реформатирована OpenAI.")
                return formatted_text, image_prompt
            else:
                # Если последняя строка не похожа на промпт, считаем всё текстом поста
                formatted_text = ai_response_text
                image_prompt = f"Abstract representation of AI and news: {news_title}" # Запасной промпт
                logger.warning("Не удалось четко выделить промпт для изображения из ответа AI, используется запасной.")
                return formatted_text, image_prompt
        else:
            # Если ответ в одну строку, считаем его текстом и генерируем дефолтный промпт
            formatted_text = ai_response_text
            image_prompt = f"Digital art illustrating the concept of: {news_title}" # Запасной промпт
            logger.warning("Ответ AI слишком короткий или не содержит явного промпта для изображения, используется запасной.")
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

async def generate_image_with_dalle(prompt: str) -> Optional[str]:
    """Генерирует изображение с помощью DALL-E OpenAI.

    Args:
        prompt: Текстовый промпт для генерации изображения.

    Returns:
        URL сгенерированного изображения или None в случае ошибки.
    """
    if not openai.api_key or not OPENAI_IMAGE_MODEL:
        logger.error("OpenAI API ключ или модель для изображений не настроены.")
        return None

    logger.info(f"Запрос на генерацию изображения DALL-E с промптом: {prompt}")
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            n=1, # Генерируем одно изображение
            size="1024x1024" # Стандартный размер
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

# Пример использования:
# if __name__ == '__main__':
#     async def test_reformat():
#         title = "Новый прорыв в квантовых вычислениях с помощью AI"
#         summary = "Ученые объявили о создании нового алгоритма AI, который значительно ускоряет квантовые расчеты."
#         link = "http://example.com/quantum-ai-breakthrough"
#         content = "Полный текст новости о том, как исследователи из Технологического Института разработали инновационный подход..."
#         
#         result = await reformat_news_for_channel(title, summary, link, content)
#         if result:
#             formatted_post, image_gen_prompt = result
#             print("--- Отформатированный пост ---")
#             print(formatted_post)
#             print(f"\n--- Промпт для изображения ---")
#             print(image_gen_prompt)
#             
#             # Тест генерации изображения
#             if image_gen_prompt:
#                 generated_image_url = await generate_image_with_dalle(image_gen_prompt)
#                 if generated_image_url:
#                     print(f"\n--- Сгенерированное изображение URL ---")
#                     print(generated_image_url)
#                 else:
#                     print("\n--- Не удалось сгенерировать изображение ---")
#         else:
#             print("Не удалось реформатировать новость.")
#     asyncio.run(test_reformat()) 