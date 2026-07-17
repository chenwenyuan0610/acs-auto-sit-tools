from __future__ import annotations

import html
import re
from typing import Any

from acs_auto_sit.challenge import visible_text_from_html


def validate_stage_fields(stage: str, fields: dict[str, Any], page: dict[str, Any] | None) -> list[dict[str, Any]]:
    visible_items = (page or {}).get("visibleText") or []
    normalized_items = [
        _normalize_text(str(item))
        for item in visible_items
        if _normalize_text(str(item))
    ]
    visible = " ".join(normalized_items)
    results: list[dict[str, Any]] = []

    for name, raw_value in fields.items():
        expected = str(raw_value or "").strip()
        if not expected:
            continue

        normalized = _normalize_text(visible_text_from_html(expected))
        pattern = _placeholder_pattern(normalized) if normalized else None
        match = next(
            (candidate for item in normalized_items if (candidate := pattern.search(item))),
            None,
        ) if pattern else None
        if match is None and pattern:
            for size in range(2, len(normalized_items) + 1):
                match = next(
                    (
                        candidate
                        for start in range(len(normalized_items) - size + 1)
                        if (
                            candidate := pattern.search(
                                " ".join(normalized_items[start : start + size])
                            )
                        )
                    ),
                    None,
                )
                if match is not None:
                    break
        matched = match is not None
        results.append(
            {
                "name": str(name),
                "stage": stage,
                "expected": expected,
                "actual": match.group(0) if match else None,
                "status": "matched" if matched else "missing",
                "found": matched,
            }
        )

    return results


def stage_page(action_results: dict[str, Any] | None, stage: str) -> dict[str, Any] | None:
    if not isinstance(action_results, dict):
        return None

    if stage == "combined":
        pages: list[dict[str, Any]] = []
        for key in ("challenge", "smsSelection", "oobSubmission", "otpSubmission", "resendSubmission"):
            page = _nested_page(action_results.get(key), key)
            if page is not None:
                pages.append(page)
        if pages:
            return {"visibleText": _merge_visible_text(pages)}
        return None

    page = _nested_page(action_results.get(stage), stage)
    if page is not None:
        return page
    for key in ("challenge", "smsSelection", "oobSubmission", "otpSubmission", "resendSubmission"):
        page = _nested_page(action_results.get(key), key)
        if page is not None:
            return page
    return None


def _nested_page(value: Any, stage: str) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("visibleText"), list):
        return {"stage": stage, "visibleText": [str(item) for item in value["visibleText"]]}
    if isinstance(value, dict):
        challenge = value.get("challenge")
        if isinstance(challenge, dict) and isinstance(challenge.get("visibleText"), list):
            return {"stage": stage, "visibleText": [str(item) for item in challenge["visibleText"]]}
    return None


def _merge_visible_text(pages: list[dict[str, Any]]) -> list[str]:
    visible: list[str] = []
    for page in pages:
        visible.extend(str(item) for item in page.get("visibleText") or [])
    return visible


def _placeholder_pattern(expected: str) -> re.Pattern[str]:
    parts = re.split(r"(\{\d+\})", expected)
    pattern: list[str] = []
    for part in parts:
        if re.fullmatch(r"\{\d+\}", part):
            pattern.append(r".+")
        else:
            tokens = [re.escape(token) for token in part.split()]
            if tokens:
                pattern.append(r"\s+".join(tokens))
    return re.compile("".join(pattern), flags=re.DOTALL)


def _normalize_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
