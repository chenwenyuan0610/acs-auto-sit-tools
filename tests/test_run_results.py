import pytest

from acs_auto_sit.run_results import normalize_completed_run, parse_areq_route


def _payload(*, selected=None, results=None):
    return {
        "runId": "20260720T001530000Z-a1b2c3d4",
        "startedAt": "2026-07-20T00:15:30.000+08:00",
        "finishedAt": "2026-07-20T00:15:32.614+08:00",
        "execution": {
            "issuerMode": "default_oob_can_switch_otp",
            "effectivePreferredChallenge": "otp",
            "wordingLocale": "zh_TW",
            "areqUrl": (
                "https://acs.example/auth/V/220/"
                "eff82784-e641-8477-3b5b-f14c2ed2ee10/123/areq"
            ),
            "selectedCaseIds": ["case01"] if selected is None else selected,
        },
        "results": [
            {
                "caseId": "case01",
                "status": "pass",
                "areqSentAt": "2026-07-20T00:15:30.214+08:00",
                "finishedAt": "2026-07-20T00:15:32.614+08:00",
                "durationMs": 2400,
                "details": {
                    "ares": {"acsTransID": "acs-1"},
                    "transactionResult": {
                        "actual": {
                            "transStatus": "Y",
                            "eci": "02",
                            "cavv": "value",
                        },
                        "mismatches": {},
                        "lookup": {"ok": True},
                    },
                },
            }
        ]
        if results is None
        else results,
    }


def test_parse_areq_route_extracts_card_scheme_and_issuer_oid():
    parsed = parse_areq_route(
        "https://acs.example/acs-auth-v3/auth/V/220/"
        "eff82784-e641-8477-3b5b-f14c2ed2ee10/123/areq"
    )

    assert parsed == {
        "cardScheme": "V",
        "issuerOid": "eff82784-e641-8477-3b5b-f14c2ed2ee10",
    }


def test_parse_areq_route_returns_empty_values_for_unknown_shape():
    assert parse_areq_route("https://acs.example/not-an-areq") == {
        "cardScheme": "",
        "issuerOid": "",
    }


def test_normalize_completed_single_case_run():
    normalized = normalize_completed_run(_payload())

    assert normalized["schemaVersion"] == 1
    assert normalized["execution"]["cardScheme"] == "V"
    assert normalized["execution"]["issuerOid"] == (
        "eff82784-e641-8477-3b5b-f14c2ed2ee10"
    )
    assert normalized["summary"] == {
        "total": 1,
        "completed": 1,
        "pass": 1,
        "fail": 0,
        "skipped": 0,
        "error": 0,
    }
    assert normalized["results"][0]["acsTransID"] == "acs-1"
    assert normalized["results"][0]["transactionResult"] == {
        "lookupStatus": "succeeded",
        "transStatus": "Y",
        "eci": "02",
        "cavvPresent": True,
        "validationStatus": "pass",
        "raw": {"transStatus": "Y", "eci": "02", "cavv": "value"},
    }


def test_normalize_completed_run_preserves_original_details_without_mutation():
    payload = _payload()

    normalized = normalize_completed_run(payload)

    assert normalized["results"][0]["details"] == payload["results"][0]["details"]
    normalized["results"][0]["details"]["ares"]["acsTransID"] = "changed"
    assert payload["results"][0]["details"]["ares"]["acsTransID"] == "acs-1"


@pytest.mark.parametrize(
    ("selected", "results", "message"),
    [
        ([], [], "at least one selected case"),
        (
            ["case01"],
            [{"caseId": "case01", "status": "running"}],
            "terminal results",
        ),
        (
            ["case01", "case02"],
            [{"caseId": "case01", "status": "pass"}],
            "terminal results",
        ),
    ],
)
def test_normalize_completed_run_rejects_invalid_completion(selected, results, message):
    with pytest.raises(ValueError, match=message):
        normalize_completed_run(_payload(selected=selected, results=results))

