import re


def strip_think_tags(text: str) -> str:
    """
    Remove <think>...</think> blocks and any stray </think> tags
    that reasoning/thinking models (e.g. DeepSeek-R1, QwQ) emit.
    """
    # Remove full <think>...</think> blocks (including multiline)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove any leftover stray closing tag
    text = text.replace("</think>", "")
    return text.strip()
