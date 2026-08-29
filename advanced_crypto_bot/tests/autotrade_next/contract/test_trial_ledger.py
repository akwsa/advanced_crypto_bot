"""Contract tests for Story 4.3: Trial Ledger and Matured Outcome."""

from datetime import UTC, datetime
import pytest

from autotrade_next.domain.trial_ledger import MaturedOutcomeTaxonomy, TrialLedgerEntry


def test_trial_ledger_entry_record():
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    entry = TrialLedgerEntry.record(
        trial_id="tr-001",
        experiment_id="exp-001",
        policy_id="pol-001",
        outcome=MaturedOutcomeTaxonomy.SCORED_SUCCESS,
        evaluated_at_utc=now,
    )

    assert entry.trial_id == "tr-001"
    assert entry.outcome is MaturedOutcomeTaxonomy.SCORED_SUCCESS
    assert entry.entry_ref.domain == "trial.entry"
