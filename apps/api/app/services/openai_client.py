from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class OpenAIError(Exception):
    pass


@dataclass(slots=True)
class OpenAIResponse:
    model: str
    content_text: str
    response_json: dict
    parsed_json: dict | None = None
    stop_reason: str | None = None
    usage: dict | None = None


class OpenAIClient:
    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self.settings = get_settings()
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.openai.com/v1"
        self.model = self.settings.openai_model or "gpt-5.4-mini"
        # Metadata from the most recent call, for safe usage logging. No secrets.
        self.last_stop_reason: str | None = None
        self.last_usage: dict | None = None
        self.last_model: str | None = None
        self.last_parse_ok: bool = True

    def _api_key(self) -> str:
        api_key = self.settings.openai_api_key
        if not api_key:
            raise OpenAIError("OpenAI API key is not configured.")
        return api_key

    def _post(self, payload: dict) -> OpenAIResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "content-type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}/responses", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OpenAIError("OpenAI request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise OpenAIError(f"OpenAI returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise OpenAIError("OpenAI request failed.") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise OpenAIError("OpenAI returned an invalid JSON response.") from exc

        content_text = _extract_output_text(response_json)
        if not content_text:
            status = response_json.get("status")
            incomplete_reason = None
            incomplete_details = response_json.get("incomplete_details")
            if isinstance(incomplete_details, dict):
                incomplete_reason = incomplete_details.get("reason")
            detail_bits = [f"status={status}"] if status else []
            if incomplete_reason:
                detail_bits.append(f"reason={incomplete_reason}")
            detail_suffix = f" ({', '.join(detail_bits)})" if detail_bits else ""
            raise OpenAIError(f"OpenAI returned no text content{detail_suffix}.")
        incomplete = response_json.get("incomplete_details")
        stop_reason = incomplete.get("reason") if isinstance(incomplete, dict) else response_json.get("status")
        return OpenAIResponse(
            model=payload["model"],
            content_text=content_text,
            response_json=response_json,
            stop_reason=stop_reason,
            usage=response_json.get("usage") if isinstance(response_json.get("usage"), dict) else None,
        )

    def generate_text(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        max_output_tokens: int = 4000,
        cache_key: str | None = None,
    ) -> OpenAIResponse:
        payload = {
            "model": model or self.model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": max_output_tokens,
        }
        # The Responses API caches stable prompt prefixes automatically; a stable
        # prompt_cache_key keeps repeated calls (same prompt template) routed to the
        # same cache so hits actually occur. It carries no secret material.
        if cache_key:
            payload["prompt_cache_key"] = cache_key
        return self._post(payload)

    def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        max_output_tokens: int = 4000,
        cache_key: str | None = None,
    ) -> dict:
        response = self.generate_text(
            instructions=instructions,
            input_text=input_text,
            model=model,
            max_output_tokens=max_output_tokens,
            cache_key=cache_key,
        )
        self.last_stop_reason = response.stop_reason
        self.last_usage = response.usage
        self.last_model = response.model
        parsed, ok = _parse_json_response_checked(response.content_text)
        self.last_parse_ok = ok
        return parsed

    def usage_metadata(self) -> dict:
        """Safe, secret-free metadata describing the most recent call."""
        from app.services.anthropic_client import _safe_usage_metadata

        return _safe_usage_metadata(
            provider="OpenAI",
            model=self.last_model or self.model,
            stop_reason=self.last_stop_reason,
            usage=self.last_usage,
        )

    def generate_json_with_web_search(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        # Reasoning + web search + a full JSON card all draw from this budget, so it
        # defaults higher than the plain generate_json path to avoid truncated JSON.
        max_output_tokens: int = 6000,
        web_search_tool_type: str = "web_search",
    ) -> OpenAIResponse:
        """Run a Responses-API call with the hosted web_search tool and parse JSON output.

        Returns the full OpenAIResponse so callers can inspect response_json for
        web_search_call items (e.g. to confirm a search actually fired). The parsed
        dict is attached on `.parsed_json`.
        """
        payload = {
            "model": model or self.model,
            "instructions": instructions,
            "input": input_text,
            "tools": [{"type": web_search_tool_type}],
            "max_output_tokens": max_output_tokens,
        }
        response = self._post(payload)
        response.parsed_json = _parse_json_response(response.content_text)
        return response


def web_search_fired(response_json: dict) -> bool:
    """True if the Responses output contains at least one web_search tool call."""
    for item in response_json.get("output") or []:
        if isinstance(item, dict) and "web_search" in str(item.get("type", "")):
            return True
    return False


def _extract_output_text(response_json: dict) -> str:
    output = response_json.get("output") or []
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(str(content["text"]))
        elif item.get("type") == "output_text" and item.get("text"):
            parts.append(str(item["text"]))
    if parts:
        return "\n".join(parts).strip()
    text_field = response_json.get("text")
    if isinstance(text_field, str):
        return text_field.strip()
    if isinstance(text_field, dict):
        for key in ("text", "value", "content", "output_text"):
            value = text_field.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                nested_parts = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
                if nested_parts:
                    return "\n".join(nested_parts).strip()
    return str(response_json.get("output_text") or "").strip()


def _parse_json_response_checked(text: str) -> tuple[dict, bool]:
    """Parse a JSON response. Returns (payload, parsed_ok).

    parsed_ok is False when the text could not be parsed as JSON and we fell back
    to a salvaged score payload.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
    try:
        return json.loads(stripped), True
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1]), True
            except json.JSONDecodeError:
                pass
        score_match = re.search(r"score[^0-9]{0,20}(\d{1,3})", stripped, re.IGNORECASE)
        if not score_match:
            score_match = re.search(r"\b(\d{1,3})\b", stripped)
        score = int(score_match.group(1)) if score_match else 0
        score = max(0, min(score, 100))
        return (
            {
                "score": score,
                "passed": score >= 85,
                "failed_checks": [],
                "warnings": [],
                "fix_instructions": [],
                "manual_override_risk": "medium",
                "summary": stripped,
            },
            False,
        )


def _parse_json_response(text: str) -> dict:
    payload, _ = _parse_json_response_checked(text)
    return payload
