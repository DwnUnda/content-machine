from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class DataForSEOError(Exception):
    pass


@dataclass(slots=True)
class DataForSEORequestResult:
    endpoint: str
    payload: list[dict]
    response_json: dict
    task: dict
    result: list[dict]
    cost: float | None


class DataForSEOClient:
    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.settings = get_settings()
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.dataforseo.com/v3"

    def _credentials(self) -> tuple[str, str]:
        login = self.settings.dataforseo_login
        password = self.settings.dataforseo_password
        if not login or not password:
            raise DataForSEOError("DataForSEO credentials are not configured.")
        return login, password

    def _post(self, endpoint: str, payload: list[dict]) -> DataForSEORequestResult:
        login, password = self._credentials()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            with httpx.Client(timeout=self.timeout_seconds, auth=(login, password)) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise DataForSEOError("DataForSEO request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise DataForSEOError(f"DataForSEO returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise DataForSEOError("DataForSEO request failed.") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise DataForSEOError("DataForSEO returned an invalid JSON response.") from exc

        status_code = response_json.get("status_code")
        if status_code and status_code != 20000:
            raise DataForSEOError(response_json.get("status_message", "DataForSEO returned an error."))

        tasks = response_json.get("tasks") or []
        if not tasks:
            raise DataForSEOError("DataForSEO returned no tasks.")

        task = tasks[0]
        task_status_code = task.get("status_code")
        if task_status_code and task_status_code != 20000:
            raise DataForSEOError(task.get("status_message", "DataForSEO task failed."))

        result = task.get("result") or []
        return DataForSEORequestResult(
            endpoint=endpoint,
            payload=payload,
            response_json=response_json,
            task=task,
            result=result,
            cost=task.get("cost") if task.get("cost") is not None else response_json.get("cost"),
        )

    def fetch_google_serp(
        self,
        keyword: str,
        *,
        location_code: int = 2036,
        language_code: str = "en",
        depth: int = 10,
    ) -> DataForSEORequestResult:
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "depth": depth,
            }
        ]
        return self._post("serp/google/organic/live/advanced", payload)

    def fetch_keyword_ideas(self, keyword: str, *, location_code: int = 2036, language_code: str = "en") -> DataForSEORequestResult:
        payload = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "include_seed_keyword": True,
                "limit": 50,
            }
        ]
        return self._post("dataforseo_labs/google/keyword_suggestions/live", payload)


def parse_serp_items(result: list[dict]) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    extras: dict[str, list[dict]] = {"people_also_ask": [], "related_searches": []}

    if not result:
        return rows, extras

    items = result[0].get("items") or []
    for item in items:
        item_type = item.get("type")
        if item_type == "organic":
            rows.append(
                {
                    "keyword": result[0].get("keyword"),
                    "position": item.get("rank_absolute"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "domain": item.get("domain"),
                    "snippet": item.get("description"),
                    "result_type": item_type,
                    "source_payload": item,
                }
            )
        elif item_type == "people_also_ask":
            extras["people_also_ask"] = item.get("items") or []
            for question in item.get("items") or []:
                rows.append(
                    {
                        "keyword": result[0].get("keyword"),
                        "position": item.get("rank_absolute"),
                        "title": question.get("title"),
                        "url": (question.get("expanded_element") or {}).get("url") if isinstance(question.get("expanded_element"), dict) else None,
                        "domain": (question.get("expanded_element") or {}).get("domain") if isinstance(question.get("expanded_element"), dict) else None,
                        "snippet": (question.get("expanded_element") or {}).get("description") if isinstance(question.get("expanded_element"), dict) else None,
                        "result_type": "people_also_ask",
                        "source_payload": question,
                    }
                )
        elif item_type == "related_searches":
            extras["related_searches"] = item.get("items") or []
            for related in item.get("items") or []:
                if isinstance(related, str):
                    rows.append(
                        {
                            "keyword": result[0].get("keyword"),
                            "position": item.get("rank_absolute"),
                            "title": related,
                            "url": None,
                            "domain": None,
                            "snippet": None,
                            "result_type": "related_searches",
                            "source_payload": {"title": related},
                        }
                    )
                    continue
                rows.append(
                    {
                        "keyword": result[0].get("keyword"),
                        "position": item.get("rank_absolute"),
                        "title": related.get("title"),
                        "url": related.get("url"),
                        "domain": related.get("domain"),
                        "snippet": related.get("description"),
                        "result_type": "related_searches",
                        "source_payload": related,
                    }
                )

    rows.sort(key=lambda entry: (entry["position"] if entry["position"] is not None else 9999, entry["result_type"] != "organic"))
    return rows, extras


def parse_keyword_ideas(result: list[dict]) -> list[dict]:
    if not result:
        return []
    suggestions = result[0].get("items") or []
    rows: list[dict] = []
    for item in suggestions:
        keyword_info = item.get("keyword_info") or {}
        rows.append(
            {
                "keyword": item.get("keyword"),
                "search_volume": keyword_info.get("search_volume"),
                "cpc": keyword_info.get("cpc"),
                "competition": keyword_info.get("competition_level") or keyword_info.get("competition"),
                "difficulty": item.get("keyword_properties", {}).get("keyword_difficulty"),
                "source": "DataForSEO Labs Keyword Suggestions",
                "notes": None,
                "source_payload": item,
            }
        )
    return rows
