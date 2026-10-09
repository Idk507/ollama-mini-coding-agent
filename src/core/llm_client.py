"""
OllamaClient — HTTP client for the Ollama /api/chat endpoint.

Default model: glm4:9b (GLM-5:cloud compatible).
Falls back gracefully when Ollama is not running.
"""

import json
from typing import Dict, List, Optional

import requests


class OllamaClient:
    """Thin wrapper around the Ollama REST API."""

    DEFAULT_MODEL = "glm4:9b"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 120,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---------------------------------------------------------------- public --
    def chat(
        self,
        prompt: str,
        system: str = None,
        history: List[Dict[str, str]] = None,
    ) -> str:
        """Send a chat message and return the model's text response."""
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

        except requests.exceptions.ConnectionError:
            return (
                "[LLM_ERROR] Cannot connect to Ollama. "
                "Make sure Ollama is running: `ollama serve`"
            )
        except requests.exceptions.Timeout:
            return "[LLM_ERROR] Request timed out."
        except requests.exceptions.HTTPError as exc:
            return f"[LLM_ERROR] HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        except (KeyError, json.JSONDecodeError) as exc:
            return f"[LLM_ERROR] Unexpected response format: {exc}"
        except Exception as exc:
            return f"[LLM_ERROR] {exc}"

    def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Return a list of locally available model names."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def select_best_model(self) -> str:
        """
        Pick the best available model.
        Priority:
          1. Local models (no ':cloud' suffix) — free, no subscription needed
          2. Any model if only cloud models exist
        """
        models = self.list_models()
        if not models:
            return self.model  # keep default; will fail gracefully

        # Prefer free local models (those without ':cloud' suffix)
        local_models = [m for m in models if not m.endswith(":cloud")]
        if local_models:
            return local_models[0]
        # All models require subscription — return first anyway
        return models[0]
