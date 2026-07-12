from __future__ import annotations

import base64
import html.parser
import json
import re
from typing import Any
from urllib.parse import urljoin


def b64url_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_b64url_json(value: str) -> dict[str, Any] | None:
    if not value:
        return None
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parsed = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


class ChallengeHtmlParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, str]] = []
        self.inputs: list[dict[str, str]] = []
        self.labels: list[dict[str, Any]] = []
        self.text_chunks: list[str] = []
        self._label: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "form":
            self.forms.append(data)
        elif tag == "input":
            self.inputs.append(data)
        elif tag == "label":
            self._label = {"attrs": data, "text": ""}
            self.labels.append(self._label)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self._label = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        self.text_chunks.append(text)
        if self._label is not None:
            self._label["text"] += text


def parse_challenge_page(html: str, source_url: str) -> dict[str, Any]:
    parser = ChallengeHtmlParser()
    parser.feed(html)

    form = parser.forms[0] if parser.forms else {}
    action = form.get("action") or source_url
    hidden_cres = _first_input_value(parser.inputs, "cres")
    decoded_cres = decode_b64url_json(hidden_cres or "")
    radio_options = [
        {
            "name": item.get("name", ""),
            "id": item.get("id", ""),
            "value": item.get("value", ""),
            "label": _label_for(parser.labels, item.get("id", "")),
        }
        for item in parser.inputs
        if item.get("type") == "radio"
    ]
    text_inputs = [
        {
            "name": item.get("name", ""),
            "id": item.get("id", ""),
            "placeholder": item.get("placeholder", ""),
        }
        for item in parser.inputs
        if item.get("type") in {"text", "password", "tel", "number"}
    ]

    fields = _form_fields(parser.inputs)
    available_actions = _available_actions(fields)

    return {
        "title": _title(html),
        "type": _page_type(radio_options, text_inputs, decoded_cres, available_actions),
        "formAction": urljoin(source_url, action),
        "formMethod": (form.get("method") or "POST").upper(),
        "fields": fields,
        "radioOptions": radio_options,
        "textInputs": text_inputs,
        "availableActions": available_actions,
        "cres": decoded_cres,
        "visibleText": parser.text_chunks[:80],
    }


def _page_type(
    radio_options: list[dict[str, str]],
    text_inputs: list[dict[str, str]],
    cres: dict[str, Any] | None,
    available_actions: dict[str, bool],
) -> str:
    if cres:
        return "cres"
    if any(item["name"] == "challengeValue" for item in radio_options):
        return "authentication_mode"
    if any(item["name"] == "challengeValue" for item in text_inputs):
        return "otp"
    if available_actions["oobContinue"]:
        return "oob"
    return "html"


def _available_actions(fields: dict[str, str]) -> dict[str, bool]:
    switch_fields = {"switchauthm", "switchAuthm", "switchToOtp", "switchToOTP", "isForceOTP"}
    return {
        "oobContinue": "oobContinue" in fields,
        "switchToOtp": any(name in fields for name in switch_fields),
    }


def _form_fields(inputs: list[dict[str, str]]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in inputs:
        name = item.get("name")
        input_type = item.get("type")
        if not name or input_type in {"radio", "checkbox", "submit", "button"}:
            continue
        fields[name] = item.get("value", "")
    return fields


def _first_input_value(inputs: list[dict[str, str]], name: str) -> str | None:
    for item in inputs:
        if item.get("name") == name:
            return item.get("value", "")
    return None


def _label_for(labels: list[dict[str, Any]], input_id: str) -> str:
    for label in labels:
        if label["attrs"].get("for") == input_id:
            return str(label["text"])
    return ""


def _title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    return " ".join(match.group(1).split()) if match else ""
