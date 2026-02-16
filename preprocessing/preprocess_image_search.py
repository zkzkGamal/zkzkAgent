import os, requests
from PIL import Image
from io import BytesIO
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PreprocessImageSearch:
    def __init__(self):
        pass

    def __call__(self, images: list[str]) -> str:
        return self.preprocess_image_search(images)

    def check_and_create_media_directory(self):
        """Check if media directory exists and create it if not"""
        try:
            if not os.path.exists("media"):
                os.makedirs("media")
                logger.info("Media directory created")
            if not os.path.exists("media/images"):
                os.makedirs("media/images")
                logger.info("Media images directory created")
        except Exception as e:
            logger.error(f"[TOOL] Media directory creation error: {e}")
            return f"Error creating media directory: {e}"

    def preprocess_image_search(self, images: list) -> str:
        self.check_and_create_media_directory()
        results = []
        for item in images:
            # Extract URL from dictionary or use string directly
            if isinstance(item, dict) and "image" in item:
                image_url = item["image"]
            elif isinstance(item, str):
                image_url = item
            else:
                logger.error(f"[TOOL] Invalid image item type: {type(item)}")
                continue

            try:
                img_data = requests.get(image_url).content
                img = Image.open(BytesIO(img_data))

                # Extract a clean filename from the URL
                filename = image_url.split("/")[-1].split("?")[0]
                if not filename:
                    filename = f"image_{len(results)}.jpg"

                img.save(f"media/images/{filename}")
                results.append(f"Image saved: {filename}\nURL: {image_url}")
            except Exception as e:
                logger.error(f"[TOOL] Image download error for {image_url}: {e}")
                results.append(f"Error downloading image {image_url}: {e}")
        return "\n\n".join(results)
