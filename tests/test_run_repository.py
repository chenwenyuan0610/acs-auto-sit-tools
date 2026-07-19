import json

import pytest

from acs_auto_sit.run_repository import RunRepository


def _run(run_id="run-1", started_at="2026-07-20T00:15:30+08:00"):
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "startedAt": started_at,
        "finishedAt": started_at,
        "execution": {"cardScheme": "V", "issuerMode": "sms_otp"},
        "summary": {"total": 1, "pass": 1},
        "results": [],
    }


def test_repository_saves_updates_and_lists_newest_first(tmp_path):
    repository = RunRepository(tmp_path)
    repository.save(_run("older", "2026-07-19T00:00:00+08:00"))
    repository.save(_run("newer", "2026-07-20T00:00:00+08:00"))
    repository.save(
        {
            **_run("newer", "2026-07-20T00:00:00+08:00"),
            "summary": {"total": 1, "pass": 0},
        }
    )

    assert [item["runId"] for item in repository.list()] == ["newer", "older"]
    assert repository.load("newer")["summary"]["pass"] == 0


def test_repository_rejects_path_like_run_id(tmp_path):
    with pytest.raises(ValueError, match="Invalid runId"):
        RunRepository(tmp_path).load("../secret")


def test_repository_reports_missing_run(tmp_path):
    with pytest.raises(FileNotFoundError):
        RunRepository(tmp_path).load("missing")


def test_repository_ignores_malformed_and_unsupported_history_files(tmp_path):
    repository = RunRepository(tmp_path)
    repository.save(_run("valid"))
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    (tmp_path / "future.json").write_text(
        json.dumps({"schemaVersion": 2, "runId": "future"}),
        encoding="utf-8",
    )

    assert [item["runId"] for item in repository.list()] == ["valid"]


def test_repository_does_not_leave_temporary_file_after_save(tmp_path):
    repository = RunRepository(tmp_path)

    repository.save(_run())

    assert (tmp_path / "run-1.json").is_file()
    assert list(tmp_path.glob("*.tmp")) == []

