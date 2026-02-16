from langchain_core.tools import tool
import ddgs
import logging , requests 
from io import BytesIO
from PIL import Image
from preprocessing.preprocess_image_search import PreprocessImageSearch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
preprocess_image_search = PreprocessImageSearch()

@tool
def duckduckgo_search_images(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo for images and save them to media/images/"""
    try:
        results = ""
        with ddgs.DDGS() as search:
            results = search.images(query=query, max_results=max_results)
            results = preprocess_image_search(results)
        return results
    except Exception as e:
        logger.error(f"[TOOL] DuckDuckGo search error: {e}")
        return f"Error searching the web: {e}"


if __name__ == "__main__":
    print(preprocess_image_search(["https://cdn.pixabay.com/photo/2016/06/24/12/53/sun-1477210_640.jpg"]))