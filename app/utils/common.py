import re
import os
import logging

logger = logging.getLogger(__name__)

def markdown_v2_escape(text: str) -> str:
    """Экранирует специальные символы для MarkdownV2."""
    # _ * [ ] ( ) ~ ` > # + - = | { } . !
    # Дефис '-' также нужно экранировать, т.к. он используется для списков и заголовков.
    escape_chars = r'([_*[\]()~`>#+\-=|{}.!])' # Добавили экранирование для дефиса
    return re.sub(escape_chars, r'\\\1', text)

def load_posted_links(file_path: str) -> set:
    """Загружает ранее опубликованные ссылки из файла."""
    posted_links = set()
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    posted_links.add(line.strip())
        except Exception as e:
            logger.error(f"Ошибка при загрузке опубликованных ссылок из {file_path}: {e}")
    return posted_links

def save_posted_link(file_path: str, link: str):
    """Сохраняет опубликованную ссылку в файл."""
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(link + '\n')
    except Exception as e:
        logger.error(f"Ошибка при сохранении ссылки {link} в файл {file_path}: {e}") 