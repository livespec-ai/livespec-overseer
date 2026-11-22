"""Temporary-store coverage for login reporting in delivery-push status."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _records(*, home: Path) -> object:
    records_module = importlib.import_module("caam_login_records")
    path = records_module.records_path(home=home)
    return records_module.load_records(path=path).records


def _save(*, home: Path, records: object) -> None:
    records_module = importlib.import_module("caam_login_records")
    records_module.save_records(path=records_module.records_path(home=home), records=records)


def _managed(*, home: Path, name: str) -> None:
    (home / ".local/share/caam/vault/claude" / name).mkdir(parents=True)


def test_status_marks_a_first_seen_managed_login_age_as_a_lower_bound(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first-seen record is rendered as an age lower bound in status."""
    status = importlib.import_module("caam_delivery_push_status")
    records_module = importlib.import_module("caam_login_records")
    account = "first-seen-account"
    _managed(home=tmp_path, name=account)
    monkeypatch.delenv("CAAM_ROTATE_LOGIN_LIFETIME_CAP_HOURS", raising=False)
    monkeypatch.delenv("CAAM_ROTATE_LOGIN_WARNING_LEAD_HOURS", raising=False)
    records = _records(home=tmp_path)
    assert records_module.note_first_seen(records=records, name=account, now=0.0)
    _save(home=tmp_path, records=records)

    lines = status.status_lines(home=tmp_path, now=86_400.0, reissue_available=True)

    assert (
        "LOGIN first-seen-account: age at least 1d 0h (lower bound), "
        "first seen 1970-01-01T00:00:00Z (first-seen)"
    ) in lines


def test_status_without_a_lifetime_cap_states_it_is_not_yet_measured(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset cap is reported without a lifetime-cap warning."""
    status = importlib.import_module("caam_delivery_push_status")
    records_module = importlib.import_module("caam_login_records")
    account = "uncapped-account"
    _managed(home=tmp_path, name=account)
    monkeypatch.delenv("CAAM_ROTATE_LOGIN_LIFETIME_CAP_HOURS", raising=False)
    monkeypatch.delenv("CAAM_ROTATE_LOGIN_WARNING_LEAD_HOURS", raising=False)
    records = _records(home=tmp_path)
    records_module.record_login(
        records=records, name=account, minted_at=0.0, source="fixture", now=0.0
    )
    _save(home=tmp_path, records=records)

    lines = status.status_lines(home=tmp_path, now=400 * 86_400.0, reissue_available=True)

    assert "LOGIN lifetime cap: not yet measured" in lines
    assert not [line for line in lines if line.startswith("WARN login lifetime cap:")]


def test_status_warns_for_a_managed_login_near_a_measured_lifetime_cap(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The warning names the managed account nearing its measured cap."""
    status = importlib.import_module("caam_delivery_push_status")
    records_module = importlib.import_module("caam_login_records")
    account = "near-cap-account"
    _managed(home=tmp_path, name=account)
    monkeypatch.setenv("CAAM_ROTATE_LOGIN_LIFETIME_CAP_HOURS", str(28 * 24))
    monkeypatch.delenv("CAAM_ROTATE_LOGIN_WARNING_LEAD_HOURS", raising=False)
    records = _records(home=tmp_path)
    records_module.record_login(
        records=records, name=account, minted_at=0.0, source="fixture", now=0.0
    )
    _save(home=tmp_path, records=records)

    lines = status.status_lines(home=tmp_path, now=27 * 86_400.0, reissue_available=True)

    assert any(
        line.startswith("WARN login lifetime cap: near-cap-account login is approaching")
        for line in lines
    )


def test_status_reports_an_unreadable_login_record_store(*, tmp_path: Path) -> None:
    """A malformed durable record store is reported rather than treated as empty."""
    status = importlib.import_module("caam_delivery_push_status")
    records_module = importlib.import_module("caam_login_records")
    path = records_module.records_path(home=tmp_path)
    path.parent.mkdir(parents=True)
    _ = path.write_text("{", encoding="utf-8")

    lines = status.status_lines(home=tmp_path, now=0.0, reissue_available=True)

    assert any(line.startswith("FAIL login records unavailable:") for line in lines)
