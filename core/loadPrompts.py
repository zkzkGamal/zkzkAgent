from langchain_core.prompts import load_prompt
import os , pathlib , logging

logger = logging.getLogger(__name__)
base_path = pathlib.Path(__file__).parent.parent

class LoadPrompts:
    def __init__(self):
        self.base_path = base_path
    
    def load_prompt(self, prompt_path):
        prompt_path = self.base_path / "prompts" / prompt_path
        prompt = load_prompt(prompt_path)
        return prompt.format_prompt(home=os.path.expanduser("~"), name="").to_messages()
