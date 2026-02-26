import json
import logging
from typing import Any, Dict

import urllib.error
import urllib.request

logger = logging.getLogger(__name__)
_API_BASE_URL = "http://<intent-management-ip>:<port>/intent"


def _http_request(
    method: str,
    url: str,
    data: bytes | None,
    headers: Dict[str, str] | None = None,
) -> str:
    headers = headers or {}
    logger.debug("HTTP %s %s", method, url)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            logger.debug("HTTP %s %s completed with status %s", method, url, response.status)
            return body
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        logger.error("HTTP %s %s failed with status %s: %s", method, url, exc.code, error_body)
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        logger.error("HTTP %s %s failed: %s", method, url, exc)
        raise RuntimeError(str(exc)) from exc


def _safe_parse(raw: str) -> Any:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return raw.strip()


def register_intent_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(contract, dict):
        raise TypeError("contract must be a dict payload")

    payload = json.dumps(contract, ensure_ascii=False).encode("utf-8")
    post_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    post_body = _http_request("POST", _API_BASE_URL, payload, post_headers)
    intent_id = contract.get("id")
    if not intent_id:
        logger.warning("No intent id provided; skipping verification")
        return {
            "post": _safe_parse(post_body),
            "get": None,
        }

    get_headers = {"Accept": "application/json"}
    get_body = _http_request("GET", f"{_API_BASE_URL}/{intent_id}", None, get_headers)

    response = {
        "post": _safe_parse(post_body),
        "get": _safe_parse(get_body),
    }
    logger.info("Intent %s registered and verified", intent_id)
    return response

