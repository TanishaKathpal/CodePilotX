# """Talking to an LLM over HTTPS.

# We use plain `requests` instead of a vendor SDK so that (a) there is one less dependency and
# (b) the exact HTTP request is visible and testable. Two providers are supported:

#   * anthropic          -> POST {base}/v1/messages           (Claude models)
#   * openai_compatible  -> POST {base}/chat/completions      (OpenAI, Ollama, vLLM, LM Studio, ...)

# Credentials and the model name come from environment variables (see config.py / .env.example).
# """
# from __future__ import annotations

# import json
# import re
# import time
# from typing import Callable, Protocol

# import requests

# from ..config import Settings

# RETRY_STATUSES = {429, 500, 502, 503, 504, 529}


# class LLMError(Exception):
#     """Any problem getting a usable answer from the model. Message is safe to show to users."""


# class LLMFormatError(LLMError):
#     """The model answered, but not in the format we asked for (worth one repair retry)."""


# class LLM(Protocol):
#     model: str

#     def complete(self, system: str, user: str) -> str: ...


# class _BaseHTTPClient:
#     def __init__(self, settings: Settings, sleep: Callable[[float], None] = time.sleep,
#                  max_retries: int = 3):
#         self.settings = settings
#         self.model = settings.llm_model
#         self._sleep = sleep
#         self._max_retries = max_retries

#     # subclasses implement
#     def _request_parts(self, system: str, user: str) -> tuple[str, dict, dict]:
#         raise NotImplementedError

#     def _parse(self, data: dict) -> str:
#         raise NotImplementedError

#     def complete(self, system: str, user: str) -> str:
#         url, headers, body = self._request_parts(system, user)
#         last_err = "unknown error"
#         for attempt in range(self._max_retries + 1):
#             try:
#                 resp = requests.post(url, headers=headers, json=body, timeout=self.settings.llm_timeout_s)
#             except requests.RequestException as e:
#                 last_err = f"network error: {type(e).__name__}"
#                 resp = None
#             if resp is not None:
#                 if resp.status_code == 200:
#                     try:
#                         return self._parse(resp.json())
#                     except (ValueError, KeyError, IndexError, TypeError) as e:
#                         raise LLMError(f"Unexpected response format from the LLM API ({type(e).__name__}).")
#                 last_err = f"HTTP {resp.status_code}: {self._error_message(resp)}"
#                 if resp.status_code in (401, 403):
#                     raise LLMError(f"The LLM API rejected the credentials ({last_err}). Check your API key.")
#                 if resp.status_code == 404:
#                     raise LLMError(f"LLM API returned 404 - check LLM_MODEL and the base URL ({last_err}).")
#                 if resp.status_code not in RETRY_STATUSES:
#                     raise LLMError(f"LLM API error ({last_err}).")
#             if attempt < self._max_retries:
#                 self._sleep(min(2 ** attempt, 8))
#         raise LLMError(f"LLM API failed after {self._max_retries + 1} attempts ({last_err}).")

#     # @staticmethod
#     # def _error_message(resp: requests.Response) -> str:
#     #     try:
#     #         data = resp.json()
#     #         err = data.get("error", data)
#     #         return str(err.get("message", err))[:300] if isinstance(err, dict) else str(err)[:300]
#     #     except ValueError:
#     #         return (resp.text or "")[:300]

#         @staticmethod
#         def _error_message(resp: requests.Response) -> str:
#             try:
#                 data = resp.json()

#                 if isinstance(data, dict):
#                     err = data.get("error", data)
#                     if isinstance(err, dict):
#                         return str(err.get("message", err))[:300]
#                     return str(err)[:300]

#                 return str(data)[:300]

#             except ValueError:
#                 return (resp.text or "")[:300]


# class AnthropicClient(_BaseHTTPClient):
#     def _request_parts(self, system, user):
#         headers = {
#             "x-api-key": self.settings.anthropic_api_key,
#             "anthropic-version": "2023-06-01",
#             "content-type": "application/json",
#         }
#         body: dict = {
#             "model": self.model,
#             "max_tokens": self.settings.llm_max_tokens,
#             "system": system,
#             "messages": [{"role": "user", "content": user}],
#         }
#         if self.settings.llm_temperature is not None:
#             body["temperature"] = self.settings.llm_temperature
#         return f"{self.settings.anthropic_base_url}/v1/messages", headers, body

#     def _parse(self, data):
#         parts = [b.get("text", "") for b in data["content"] if b.get("type") == "text"]
#         text = "".join(parts).strip()
#         if not text:
#             raise ValueError("empty content")
#         return text


# class OpenAICompatibleClient(_BaseHTTPClient):
#     def _request_parts(self, system, user):
#         headers = {"content-type": "application/json"}
#         if self.settings.openai_api_key:
#             headers["authorization"] = f"Bearer {self.settings.openai_api_key}"
#         body: dict = {
#             "model": self.model,
#             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
#         }
#         if self.settings.llm_temperature is not None:
#             body["temperature"] = self.settings.llm_temperature
#         return f"{self.settings.openai_base_url}/chat/completions", headers, body

#     def _parse(self, data):
#         text = (data["choices"][0]["message"]["content"] or "").strip()
#         if not text:
#             raise ValueError("empty content")
#         return text


# def get_llm(settings: Settings, **kwargs) -> LLM | None:
#     """Return a client, or None when no credentials are configured (the app then runs in
#     'retrieval only' mode and says so)."""
#     if settings.llm_provider == "anthropic":
#         return AnthropicClient(settings, **kwargs) if settings.anthropic_api_key else None
#     if settings.llm_provider == "openai_compatible":
#         # Local servers (Ollama etc.) need no key, but then a non-default base URL must be set.
#         local = settings.openai_base_url != "https://api.openai.com/v1"
#         return OpenAICompatibleClient(settings, **kwargs) if (settings.openai_api_key or local) else None
#     raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r} (use 'anthropic' or 'openai_compatible')")


# # ------------------------------------------------------------------ JSON extraction

# _FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.IGNORECASE)


# def extract_json(text: str) -> dict:
#     """Pull one JSON object out of a model reply (tolerates code fences and surrounding prose)."""
#     cleaned = _FENCE_RE.sub("", text.strip()).strip()
#     try:
#         obj = json.loads(cleaned)
#         if isinstance(obj, dict):
#             return obj
#     except json.JSONDecodeError:
#         pass
#     start = cleaned.find("{")
#     while start != -1:
#         depth, in_str, esc = 0, False, False
#         for i in range(start, len(cleaned)):
#             ch = cleaned[i]
#             if in_str:
#                 if esc:
#                     esc = False
#                 elif ch == "\\":
#                     esc = True
#                 elif ch == '"':
#                     in_str = False
#             elif ch == '"':
#                 in_str = True
#             elif ch == "{":
#                 depth += 1
#             elif ch == "}":
#                 depth -= 1
#                 if depth == 0:
#                     try:
#                         obj = json.loads(cleaned[start:i + 1])
#                         if isinstance(obj, dict):
#                             return obj
#                     except json.JSONDecodeError:
#                         break
#         start = cleaned.find("{", start + 1)
#     raise LLMFormatError("The model did not return valid JSON.")




"""Talking to an LLM over HTTPS.

We use plain `requests` instead of a vendor SDK so that (a) there is one less dependency and
(b) the exact HTTP request is visible and testable. Two providers are supported:

  * anthropic          -> POST {base}/v1/messages           (Claude models)
  * openai_compatible  -> POST {base}/chat/completions      (OpenAI, Ollama, vLLM, LM Studio, ...)

Credentials and the model name come from environment variables (see config.py / .env.example).
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable, Protocol

import requests

from ..config import Settings

RETRY_STATUSES = {429, 500, 502, 503, 504, 529}


class LLMError(Exception):
    """Any problem getting a usable answer from the model. Message is safe to show to users."""


class LLMFormatError(LLMError):
    """The model answered, but not in the format we asked for (worth one repair retry)."""


class LLM(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


class _BaseHTTPClient:
    def __init__(
        self,
        settings: Settings,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
    ):
        self.settings = settings
        self.model = settings.llm_model
        self._sleep = sleep
        self._max_retries = max_retries

    # Subclasses implement these methods.
    def _request_parts(self, system: str, user: str) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def _parse(self, data: dict) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str) -> str:
        url, headers, body = self._request_parts(system, user)
        last_err = "unknown error"

        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=self.settings.llm_timeout_s,
                )
            except requests.RequestException as e:
                last_err = f"network error: {type(e).__name__}"
                resp = None

            if resp is not None:
                if resp.status_code == 200:
                    try:
                        return self._parse(resp.json())
                    except (ValueError, KeyError, IndexError, TypeError) as e:
                        raise LLMError(
                            f"Unexpected response format from the LLM API ({type(e).__name__})."
                        )

                last_err = f"HTTP {resp.status_code}: {self._error_message(resp)}"

                if resp.status_code in (401, 403):
                    raise LLMError(
                        f"The LLM API rejected the credentials ({last_err}). Check your API key."
                    )

                if resp.status_code == 404:
                    raise LLMError(
                        f"LLM API returned 404 - check LLM_MODEL and the base URL ({last_err})."
                    )

                if resp.status_code not in RETRY_STATUSES:
                    raise LLMError(f"LLM API error ({last_err}).")

            if attempt < self._max_retries:
                self._sleep(min(2 ** attempt, 8))

        raise LLMError(
            f"LLM API failed after {self._max_retries + 1} attempts ({last_err})."
        )

    @staticmethod
    def _error_message(resp: requests.Response) -> str:
        try:
            data = resp.json()

            if isinstance(data, dict):
                err = data.get("error", data)

                if isinstance(err, dict):
                    return str(err.get("message", err))[:300]

                return str(err)[:300]

            return str(data)[:300]

        except ValueError:
            return (resp.text or "")[:300]


class AnthropicClient(_BaseHTTPClient):
    def _request_parts(self, system, user):
        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        body: dict = {
            "model": self.model,
            "max_tokens": self.settings.llm_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

        if self.settings.llm_temperature is not None:
            body["temperature"] = self.settings.llm_temperature

        return f"{self.settings.anthropic_base_url}/v1/messages", headers, body

    def _parse(self, data):
        parts = [
            b.get("text", "")
            for b in data["content"]
            if b.get("type") == "text"
        ]

        text = "".join(parts).strip()

        if not text:
            raise ValueError("empty content")

        return text


class OpenAICompatibleClient(_BaseHTTPClient):
    def _request_parts(self, system, user):
        headers = {"content-type": "application/json"}

        if self.settings.openai_api_key:
            headers["authorization"] = (
                f"Bearer {self.settings.openai_api_key}"
            )

        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        if self.settings.llm_temperature is not None:
            body["temperature"] = self.settings.llm_temperature

        return (
            f"{self.settings.openai_base_url}/chat/completions",
            headers,
            body,
        )

    def _parse(self, data):
        text = (
            data["choices"][0]["message"]["content"] or ""
        ).strip()

        if not text:
            raise ValueError("empty content")

        return text


def get_llm(settings: Settings, **kwargs) -> LLM | None:
    """Return a client, or None when no credentials are configured."""

    if settings.llm_provider == "anthropic":
        return (
            AnthropicClient(settings, **kwargs)
            if settings.anthropic_api_key
            else None
        )

    if settings.llm_provider == "openai_compatible":
        # Local servers (Ollama etc.) need no key, but then a non-default base URL must be set.
        local = settings.openai_base_url != "https://api.openai.com/v1"

        return (
            OpenAICompatibleClient(settings, **kwargs)
            if (settings.openai_api_key or local)
            else None
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER {settings.llm_provider!r} "
        "(use 'anthropic' or 'openai_compatible')"
    )


# ------------------------------------------------------------------
# JSON extraction

_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?|\n?```\s*$",
    re.IGNORECASE,
)


def extract_json(text: str) -> dict:
    """Pull one JSON object out of a model reply (tolerates code fences and surrounding prose)."""

    cleaned = _FENCE_RE.sub("", text.strip()).strip()

    try:
        obj = json.loads(cleaned)

        if isinstance(obj, dict):
            return obj

    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")

    while start != -1:
        depth = 0
        in_str = False
        esc = False

        for i in range(start, len(cleaned)):
            ch = cleaned[i]

            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False

            elif ch == '"':
                in_str = True

            elif ch == "{":
                depth += 1

            elif ch == "}":
                depth -= 1

                if depth == 0:
                    try:
                        obj = json.loads(cleaned[start:i + 1])

                        if isinstance(obj, dict):
                            return obj

                    except json.JSONDecodeError:
                        break

        start = cleaned.find("{", start + 1)

    raise LLMFormatError("The model did not return valid JSON.")
