import asyncio
import logging
import aiohttp
from readability import Document
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

async def fetch_article_content(url: str, session: aiohttp.ClientSession) -> str | None:
    """
    Fetches the main article content from a given URL.

    Args:
        url: The URL of the article.
        session: An aiohttp.ClientSession instance for making HTTP requests.

    Returns:
        The cleaned HTML content of the main article, or None if fetching/parsing fails.
    """
    if not url:
        logger.warning("No URL provided to fetch_article_content.")
        return None

    logger.info(f"Attempting to fetch full article content from: {url}")
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as response:
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            html_content = await response.text()
            
            if not html_content:
                logger.warning(f"No HTML content received from {url}")
                return None

            # Use readability to extract the main content
            doc = Document(html_content)
            article_html_summary = doc.summary() # This gives HTML of the main article

            if not article_html_summary:
                logger.warning(f"Readability could not extract main content from {url}")
                return None

            # At this point, article_html_summary contains the HTML of the main article.
            # We can use BeautifulSoup to further clean or transform it if needed.
            # For now, let's return the direct HTML output from readability.
            # Example: Convert to plain text (stripping all HTML tags)
            # soup = BeautifulSoup(article_html_summary, 'html.parser')
            # plain_text_content = soup.get_text(separator='\n', strip=True)
            # return plain_text_content
            
            logger.info(f"Successfully extracted main content from {url} using readability.")
            return article_html_summary

    except aiohttp.ClientError as e:
        logger.error(f"aiohttp error while fetching article {url}: {e}", exc_info=False) # exc_info=False for brevity
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching or parsing article {url}: {e}", exc_info=True)
        return None

# Example usage (for testing this service directly)
# if __name__ == '__main__':
#     async def main():
#         # Example URL - replace with a real article URL for testing
#         test_url = "https://www.wired.com/story/our-minds-are-no-match-for-our-digital-media/"
        
#         # It's good practice to create the session once and pass it around
#         async with aiohttp.ClientSession() as session:
#             content = await fetch_article_content(test_url, session)
        
#         if content:
#             print(f"--- Extracted Content from {test_url} ---")
#             # If returning HTML:
#             print(content[:1000] + "..." if len(content) > 1000 else content) 
            
#             # If returning plain text:
#             # print(content)
#             print("\n--- End of Content ---")
#         else:
#             print(f"Failed to extract content from {test_url}")

#     # Setup basic logging to see output
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
#     asyncio.run(main()) 