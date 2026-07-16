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
        self.buttons: list[dict[str, str]] = []
        self.labels: list[dict[str, Any]] = []
        self.text_chunks: list[str] = []
        self._label: dict[str, Any] | None = None
        self._button: dict[str, str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if self._ignored_depth:
            if tag in {"script", "style", "template", "noscript"}:
                self._ignored_depth += 1
            return
        if tag in {"script", "style", "template", "noscript"}:
            self._ignored_depth = 1
            return
        if tag == "form":
            self.forms.append(data)
        elif tag == "input":
            self.inputs.append(data)
            self._append_attribute_text(tag, data)
        elif tag == "button":
            self._append_attribute_text(tag, data)
            data["text"] = ""
            self.buttons.append(data)
            self._button = data
        elif tag == "label":
            self._label = {"attrs": data, "text": ""}
            self.labels.append(self._label)
        else:
            self._append_attribute_text(tag, data)

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            if tag in {"script", "style", "template", "noscript"}:
                self._ignored_depth -= 1
            return
        if tag == "label":
            self._label = None
        elif tag == "button":
            self._button = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        self.text_chunks.append(text)
        if self._label is not None:
            self._label["text"] += text
        if self._button is not None:
            self._button["text"] += text

    def _append_attribute_text(self, tag: str, attrs: dict[str, str]) -> None:
        texts: list[str] = []
        input_type = attrs.get("type", "").lower()
        if tag == "input" and input_type in {"text", "password", "tel", "number", "submit", "button"}:
            texts.extend([attrs.get("placeholder", ""), attrs.get("value", "")])
        texts.extend([attrs.get("aria-label", ""), attrs.get("title", ""), attrs.get("alt", "")])
        for value in texts:
            text = " ".join(str(value).split())
            if text:
                self.text_chunks.append(text)


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
    action_controls = _action_controls(parser.inputs, parser.buttons)
    available_actions = _available_actions(fields, action_controls)

    return {
        "rawHtml": html,
        "title": _title(html),
        "type": _page_type(radio_options, text_inputs, decoded_cres, available_actions),
        "formAction": urljoin(source_url, action),
        "formMethod": (form.get("method") or "POST").upper(),
        "fields": fields,
        "actionControls": action_controls,
        "radioOptions": radio_options,
        "textInputs": text_inputs,
        "availableActions": available_actions,
        "cres": decoded_cres,
        "visibleText": parser.text_chunks[:80],
    }


def visible_text_from_html(value: str) -> str:
    parser = ChallengeHtmlParser()
    parser.feed(str(value or ""))
    return " ".join(parser.text_chunks)


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


def _available_actions(fields: dict[str, str], action_controls: list[dict[str, str]]) -> dict[str, bool]:
    switch_fields = {"switchauthm", "switchAuthm", "switchToOtp", "switchToOTP", "isForceOTP"}
    return {
        "oobContinue": "oobContinue" in fields,
        "switchToOtp": any(name in fields for name in switch_fields),
        "resendOtp": _has_resend_control(fields, action_controls),
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


def _action_controls(inputs: list[dict[str, str]], buttons: list[dict[str, str]]) -> list[dict[str, str]]:
    controls: list[dict[str, str]] = []
    for item in inputs:
        input_type = item.get("type", "")
        if input_type not in {"submit", "button"}:
            continue
        controls.append(
            {
                "name": item.get("name", ""),
                "id": item.get("id", ""),
                "value": item.get("value", ""),
                "type": input_type,
                "text": "",
            }
        )
    for item in buttons:
        controls.append(
            {
                "name": item.get("name", ""),
                "id": item.get("id", ""),
                "value": item.get("value", ""),
                "type": item.get("type", "button"),
                "text": item.get("text", ""),
            }
        )
    return controls


def _has_resend_control(fields: dict[str, str], action_controls: list[dict[str, str]]) -> bool:
    resend_terms = (
        "resend",
        "重新获取验证码",
        "ส่งรหัสอีกครั้ง",
        "ផ្ញើលេខកូដឡើងវិញ",
    )
    field_blob = " ".join(fields.keys()).lower()
    if "resend" in field_blob:
        return True
    for control in action_controls:
        text = " ".join(
            str(control.get(key, ""))
            for key in ("name", "id", "value", "text")
        )
        lower_text = text.lower()
        if any(term in lower_text or term in text for term in resend_terms):
            return True
    return False


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
