from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class AnthropicError(Exception):
    pass


@dataclass(slots=True)
class AnthropicResponse:
    model: str
    content_text: str
    response_json: dict
    stop_reason: str | None = None
    usage: dict | None = None


class AnthropicClient:
    def __init__(self, timeout_seconds: float = 600.0) -> None:
        self.settings = get_settings()
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.anthropic.com/v1"
        self.model = self.settings.anthropic_model or "claude-sonnet-4-6"
        # Metadata from the most recent call, used by callers for truncation
        # detection and safe usage logging. Never holds secrets.
        self.last_stop_reason: str | None = None
        self.last_usage: dict | None = None
        self.last_model: str | None = None
        self.last_parse_ok: bool = True

    def _api_key(self) -> str:
        api_key = self.settings.anthropic_api_key
        if not api_key:
            raise AnthropicError("Anthropic API key is not configured.")
        return api_key

    def _post(self, payload: dict) -> AnthropicResponse:
        headers = {
            "x-api-key": self._api_key(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Use separate connect vs read timeouts. The Anthropic non-streaming API
        # generates the full response server-side before returning any bytes, so
        # for large outputs (16k tokens on a longform article) the read phase can
        # legitimately take 5-10 minutes.
        timeout = httpx.Timeout(
            connect=30.0,
            read=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=self.timeout_seconds,
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(f"{self.base_url}/messages", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AnthropicError("Anthropic request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise AnthropicError(f"Anthropic returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise AnthropicError("Anthropic request failed.") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise AnthropicError("Anthropic returned an invalid JSON response.") from exc

        content = response_json.get("content") or []
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                text_parts.append(str(item["text"]))
        content_text = "\n".join(text_parts).strip()
        if not content_text:
            raise AnthropicError("Anthropic returned no text content.")
        return AnthropicResponse(
            model=payload["model"],
            content_text=content_text,
            response_json=response_json,
            stop_reason=response_json.get("stop_reason"),
            usage=response_json.get("usage") if isinstance(response_json.get("usage"), dict) else None,
        )

    def _system_blocks(self, system_prompt: str, *, cache: bool) -> list | str:
        """Return the system field, marking it cacheable when requested.

        The system prompt (prompt template text + any stable packet) is identical
        across the first_draft, human polish and fix passes within a run, so
        caching it cuts repeated input tokens without changing the content the
        model sees.
        """
        if not cache:
            return system_prompt
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 4000,
        cache: bool = True,
    ) -> AnthropicResponse:
        payload = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "system": self._system_blocks(system_prompt, cache=cache),
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = self._post(payload)
        self.last_stop_reason = response.stop_reason
        self.last_usage = response.usage
        self.last_model = response.model
        self.last_parse_ok = True
        return response

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 4000,
        cache: bool = True,
    ) -> dict:
        response = self.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=max_tokens,
            cache=cache,
        )
        self.last_stop_reason = response.stop_reason
        self.last_usage = response.usage
        self.last_model = response.model
        parsed, ok = _parse_json_response_checked(response.content_text)
        self.last_parse_ok = ok
        return parsed

    def usage_metadata(self) -> dict:
        """Safe, secret-free metadata describing the most recent call."""
        return _safe_usage_metadata(
            provider="Anthropic",
            model=self.last_model or self.model,
            stop_reason=self.last_stop_reason,
            usage=self.last_usage,
        )


def _safe_usage_metadata(*, provider: str, model: str | None, stop_reason: str | None, usage: dict | None) -> dict:
    """Build secret-free token/usage metadata for logging.

    Only numeric token counts, the model name and the stop reason are included;
    API keys and raw request payloads are never touched here.
    """
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    # Anthropic reports cache token counts at the top level; OpenAI nests cached
    # input tokens under input_tokens_details.
    cache_write = usage.get("cache_creation_input_tokens")
    cache_read = usage.get("cache_read_input_tokens")
    details = usage.get("input_tokens_details")
    if cache_read is None and isinstance(details, dict):
        cache_read = details.get("cached_tokens")
    return {
        "provider": provider,
        "model": model,
        "stop_reason": stop_reason,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }


def _parse_json_response_checked(text: str) -> tuple[dict, bool]:
    """Parse a JSON response. Returns (payload, parsed_ok).

    parsed_ok is False when the model output could not be parsed as JSON and we
    fell back to wrapping the raw text. Callers use this to reject truncated or
    corrupted drafts instead of saving the raw blob as the article body.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
    try:
        return json.loads(stripped), True
    except json.JSONDecodeError:
        match = stripped.find("{")
        end = stripped.rfind("}")
        if match != -1 and end != -1 and end > match:
            try:
                return json.loads(stripped[match : end + 1]), True
            except json.JSONDecodeError:
                pass
        return (
            {
                "draft_markdown": text.strip(),
                "notes": [],
                "title_options": [],
            },
            False,
        )


def _parse_json_response(text: str) -> dict:
    payload, _ = _parse_json_response_checked(text)
    return payload
