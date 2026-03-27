# integrations/llm.py
import requests

class OllamaClient:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 1000) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 4096,           # Фиксированный контекст
                "temperature": 0.1,        # Минимум креативности
                "top_p": 0.8,
                "repeat_penalty": 1.2,     # Штраф повторений
                "seed": 42                 # Фиксированный сид для стабильности
            }
        }

        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload, timeout=500
        )
        return resp.json()["response"]
