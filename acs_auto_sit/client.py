from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlencode


@dataclass(slots=True)
class PostResult:
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: Any
    status_code: int | None
    response_headers: dict[str, str]
    response_text: str
    response_json: Any
    elapsed_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def post_payload(
    url: str,
    payload: Any,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    use_system_proxy: bool = False,
) -> PostResult:
    headers = dict(headers or {})
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    started = time.perf_counter()
    req = request.Request(url, data=body, headers=headers, method="POST")
    opener = request.build_opener() if use_system_proxy else request.build_opener(request.ProxyHandler({}))

    try:
        with opener.open(req, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return _build_result(
                url=url,
                headers=headers,
                payload=payload,
                status_code=response.status,
                response_headers=dict(response.headers.items()),
                response_text=response_body,
                elapsed_ms=_elapsed_ms(started),
            )
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return _build_result(
            url=url,
            headers=headers,
            payload=payload,
            status_code=exc.code,
            response_headers=dict(exc.headers.items()),
            response_text=response_body,
            elapsed_ms=_elapsed_ms(started),
            error=str(exc),
        )
    except error.URLError as exc:
        return _build_result(
            url=url,
            headers=headers,
            payload=payload,
            status_code=None,
            response_headers={},
            response_text="",
            elapsed_ms=_elapsed_ms(started),
            error=str(exc.reason),
        )


def post_form(
    url: str,
    form: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    use_system_proxy: bool = False,
) -> PostResult:
    headers = dict(headers or {})
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

    body = urlencode(form).encode("utf-8")
    started = time.perf_counter()
    req = request.Request(url, data=body, headers=headers, method="POST")
    opener = request.build_opener() if use_system_proxy else request.build_opener(request.ProxyHandler({}))

    try:
        with opener.open(req, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return _build_result(
                url=url,
                headers=headers,
                payload=form,
                status_code=response.status,
                response_headers=dict(response.headers.items()),
                response_text=response_body,
                elapsed_ms=_elapsed_ms(started),
            )
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return _build_result(
            url=url,
            headers=headers,
            payload=form,
            status_code=exc.code,
            response_headers=dict(exc.headers.items()),
            response_text=response_body,
            elapsed_ms=_elapsed_ms(started),
            error=str(exc),
        )
    except error.URLError as exc:
        return _build_result(
            url=url,
            headers=headers,
            payload=form,
            status_code=None,
            response_headers={},
            response_text="",
            elapsed_ms=_elapsed_ms(started),
            error=str(exc.reason),
        )


def _build_result(
    url: str,
    headers: dict[str, str],
    payload: Any,
    status_code: int | None,
    response_headers: dict[str, str],
    response_text: str,
    elapsed_ms: int,
    error: str | None = None,
) -> PostResult:
    return PostResult(
        method="POST",
        url=url,
        request_headers=headers,
        request_body=payload,
        status_code=status_code,
        response_headers=response_headers,
        response_text=response_text,
        response_json=_parse_json(response_text),
        elapsed_ms=elapsed_ms,
        error=error,
    )


def _parse_json(value: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
