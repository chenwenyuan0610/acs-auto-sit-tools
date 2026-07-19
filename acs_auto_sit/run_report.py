from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from typing import Any


def html_report_filename(run: dict[str, Any]) -> str:
    execution = run.get("execution") if isinstance(run.get("execution"), dict) else {}
    case_ids = (
        execution.get("selectedCaseIds")
        if isinstance(execution.get("selectedCaseIds"), list)
        else []
    )
    scope = str(case_ids[0]) if len(case_ids) == 1 else f"{len(case_ids)}-cases"
    scheme = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        str(execution.get("cardScheme") or "unknown"),
    ).strip("-") or "unknown"
    started = datetime.fromisoformat(str(run["startedAt"]).replace("Z", "+00:00"))
    return f"sit-report-{scheme}-{scope}-{started:%Y%m%d-%H%M%S}.html"


def render_html_report(run: dict[str, Any]) -> bytes:
    execution = run.get("execution") if isinstance(run.get("execution"), dict) else {}
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
    results = run.get("results") if isinstance(run.get("results"), list) else []
    rows = "".join(_case_row(item) for item in results if isinstance(item, dict))
    details = "".join(_case_details(item) for item in results if isinstance(item, dict))
    document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ACS Auto SIT Report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 24px; line-height: 1.5; }}
    h1, h2 {{ margin-block: 0 16px; }}
    dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }}
    dt {{ font-weight: 600; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 12px; margin: 20px 0; }}
    .metric {{ border: 1px solid currentColor; border-radius: 8px; padding: 12px; }}
    .metric strong {{ display: block; font-size: 1.5rem; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid currentColor; text-align: left; vertical-align: top; }}
    code, pre {{ font-family: ui-monospace, monospace; overflow-wrap: anywhere; }}
    pre {{ white-space: pre-wrap; }} details {{ margin-top: 12px; }}
  </style>
</head>
<body>
  <h1>ACS Auto SIT Report</h1>
  <dl>
    <dt>Issuer mode</dt><dd>{_text(execution.get("issuerMode"))}</dd>
    <dt>Preferred challenge</dt><dd>{_text(execution.get("effectivePreferredChallenge"))}</dd>
    <dt>Locale</dt><dd>{_text(execution.get("wordingLocale"))}</dd>
    <dt>Card scheme</dt><dd>{_text(execution.get("cardScheme"))}</dd>
    <dt>Issuer OID</dt><dd>{_text(execution.get("issuerOid"))}</dd>
    <dt>Started</dt><dd>{_text(run.get("startedAt"))}</dd>
    <dt>Finished</dt><dd>{_text(run.get("finishedAt"))}</dd>
  </dl>
  <section class="metrics" aria-label="Run summary">
    {_metric("Total", summary.get("total"))}
    {_metric("Pass", summary.get("pass"))}
    {_metric("Fail", summary.get("fail"))}
    {_metric("Skipped", summary.get("skipped"))}
    {_metric("Error", summary.get("error"))}
  </section>
  <h2>Case results</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Case</th><th>Status</th><th>AReq sent</th><th>acsTransID</th><th>Transaction result</th><th>Duration</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <h2>Case details</h2>
  {details}
</body>
</html>"""
    return document.encode("utf-8")


def _metric(label: str, value: Any) -> str:
    return f'<div class="metric"><span>{_text(label)}</span><strong>{_text(value)}</strong></div>'


def _case_row(item: dict[str, Any]) -> str:
    transaction = (
        item.get("transactionResult")
        if isinstance(item.get("transactionResult"), dict)
        else {}
    )
    transaction_summary = " · ".join(
        part
        for part in (
            str(transaction.get("transStatus") or ""),
            f"ECI {transaction['eci']}" if transaction.get("eci") else "",
            "CAVV present" if transaction.get("cavvPresent") else "CAVV absent",
            str(transaction.get("lookupStatus") or ""),
        )
        if part
    )
    duration = item.get("durationMs")
    duration_text = f"{duration} ms" if duration not in (None, "") else "—"
    return (
        "<tr>"
        f"<td>{_text(item.get('caseId'))}</td>"
        f"<td>{_text(item.get('status'))}</td>"
        f"<td>{_text(item.get('areqSentAt'))}</td>"
        f"<td><code>{_text(item.get('acsTransID'))}</code></td>"
        f"<td>{_text(transaction_summary)}</td>"
        f"<td>{_text(duration_text)}</td>"
        "</tr>"
    )


def _case_details(item: dict[str, Any]) -> str:
    detail_text = json.dumps(
        {
            "reason": item.get("reason"),
            "transactionResult": item.get("transactionResult"),
            "details": item.get("details"),
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        "<details>"
        f"<summary>{_text(item.get('caseId'))} · {_text(item.get('status'))}</summary>"
        f"<pre>{_text(detail_text)}</pre>"
        "</details>"
    )


def _text(value: Any) -> str:
    return escape(str(value if value not in (None, "") else "—"), quote=True)
