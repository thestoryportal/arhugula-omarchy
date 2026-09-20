import unittest

from runtime.evaluation import ReplayRun
from runtime.projections import Projection


class Journal:
    """Synthetic journal with only the freshness surface the adapter needs."""

    def __init__(self, entries=()):
        self.entries = tuple(entries)

    def read(self, *, after=0):
        return tuple(entry for cursor, entry in self.entries if cursor > after)


class ObservabilityAdapterTests(unittest.TestCase):
    def test_current_snapshot_exposes_detached_public_data_and_review_evidence(self):
        """Public observation is copied evidence; it never becomes an action capability."""
        from runtime.observability_adapter import (
            Available,
            DetailEvidence,
            ProjectionEvidence,
            ReviewEvidence,
            snapshot,
        )

        projection = Projection(4, {"status": "success", "event_type": "command.finished"},
                                {"phase": "voice.preview"}, "lane-1",
                                {"id": "local", "model_version": "v1", "status": "success"})
        diagnostics = [
            {"category": "timing", "value": {"duration_ms": 18}, "sensitivity": "public"},
            {"category": "transcript", "value": "private words", "sensitivity": "private"},
        ]
        active = ReplayRun("active-v1", "synthetic", "bundle-1", True, True, True,
                           {"case-1": "pass"}, True)
        candidate = ReplayRun("candidate-v2", "synthetic", "bundle-1", True, True, True,
                              {"case-1": "pass"}, True)

        # [LAW:behavior-not-structure] The contract is the returned evidence, not its helpers.
        observed = snapshot(
            compact=Available(ProjectionEvidence(projection, Journal())),
            detail=Available(DetailEvidence(projection, Journal(), diagnostics)),
            review=Available(ReviewEvidence(active, candidate, ("approved",), True)),
        )

        self.assertEqual(observed, {
            "version": "observability-adapter/v1",
            "compact": {
                "source_state": "available", "freshness": "current",
                "data": {
                    "cursor": 4, "lane": "lane-1", "action_status": "success",
                    "interaction_phase": "voice.preview", "provider_status": "success",
                    "active_mode": None, "muted": None, "health": None,
                    "degraded_capabilities": [], "pending": False, "voice_lifecycle": {},
                },
            },
            "detail": {
                "source_state": "available", "freshness": "current",
                "data": {
                    "state": {
                        "cursor": 4, "lane": "lane-1", "action_status": "success",
                        "interaction_phase": "voice.preview", "provider_status": "success",
                        "active_mode": None, "muted": None, "health": None,
                        "degraded_capabilities": [], "pending": False, "voice_lifecycle": {},
                    },
                    "diagnostics": [{"category": "timing", "value": {"duration_ms": 18}}],
                },
            },
            "review": {
                "source_state": "available", "freshness": "not-applicable",
                "evidence": {"comparison": "qualified", "regressions": [], "reasons": []},
            },
        })
        observed["detail"]["data"]["diagnostics"][0]["value"]["duration_ms"] = 99
        self.assertEqual(diagnostics[0]["value"], {"duration_ms": 18})
        self.assertNotIn("promote", observed["review"])
        self.assertNotIn("dispatch", observed["review"])

    def test_empty_projection_is_stale_when_the_injected_journal_has_later_entries(self):
        """Freshness remains evidence about the supplied source rather than a refresh request."""
        from runtime.observability_adapter import Available, ProjectionEvidence, Unreadable, snapshot

        projection = Projection(0, None, None, None, None)
        later_entry = object()

        observed = snapshot(
            compact=Available(ProjectionEvidence(projection, Journal(((1, later_entry),)))),
            detail=Unreadable(),
            review=Unreadable(),
        )

        self.assertEqual(observed["compact"], {
            "source_state": "available", "freshness": "stale",
            "data": {
                "cursor": 0, "lane": None, "action_status": None, "interaction_phase": None,
                "provider_status": None, "active_mode": None, "muted": None, "health": None,
                "degraded_capabilities": [], "pending": False, "voice_lifecycle": {},
            },
        })
        self.assertEqual(observed["detail"], {
            "source_state": "unreadable", "freshness": "unknown",
        })
        self.assertEqual(observed["review"], {
            "source_state": "unreadable", "freshness": "unknown",
        })

    def test_unreadable_and_contradictory_sources_remain_explicit_errors(self):
        """Source failures cannot be replaced with healthy-looking empty evidence."""
        from runtime.observability_adapter import Contradictory, Unreadable, snapshot

        observed = snapshot(
            compact=Contradictory(),
            detail=Unreadable(),
            review=Contradictory(),
        )

        # [LAW:no-silent-failure] Each source keeps its failure state instead of a fallback.
        self.assertEqual(observed, {
            "version": "observability-adapter/v1",
            "compact": {"source_state": "contradictory", "freshness": "unknown"},
            "detail": {"source_state": "unreadable", "freshness": "unknown"},
            "review": {"source_state": "contradictory", "freshness": "unknown"},
        })

    def test_detail_rejects_nested_private_or_unknown_classifications(self):
        """A public diagnostic envelope cannot launder nested classified content."""
        from runtime.observability_adapter import Available, DetailEvidence, Unreadable, snapshot

        projection = Projection(0, None, None, None, None)
        for value in (
            {"nested": {"sensitivity": "private", "value": "secret"}},
            {"items": [{"sensitivity": "unknown", "value": "secret"}]},
        ):
            with self.subTest(value=value):
                observed = snapshot(
                    compact=Unreadable(),
                    detail=Available(DetailEvidence(projection, Journal(), [
                        {"category": "timing", "value": value, "sensitivity": "public"},
                    ])),
                    review=Unreadable(),
                )

                # [LAW:no-silent-failure] Unsafe nested evidence becomes an explicit source error.
                self.assertEqual(observed["detail"], {
                    "source_state": "unreadable", "freshness": "unknown",
                })

    def test_detail_detaches_nested_public_mapping_and_sequence_values(self):
        """Structured public evidence is copied without retaining aliases to source values."""
        from runtime.observability_adapter import Available, DetailEvidence, Unreadable, snapshot

        value = {
            "nested": {"sensitivity": "public", "duration_ms": 18},
            "items": [{"sensitivity": "public", "counts": [1, 2]}],
        }
        observed = snapshot(
            compact=Unreadable(),
            detail=Available(DetailEvidence(Projection(0, None, None, None, None), Journal(), [
                {"category": "timing", "value": value, "sensitivity": "public"},
            ])),
            review=Unreadable(),
        )

        self.assertEqual(observed["detail"]["source_state"], "available")
        observed["detail"]["data"]["diagnostics"][0]["value"]["items"][0]["counts"].append(3)
        self.assertEqual(value["items"][0]["counts"], [1, 2])


if __name__ == "__main__":
    unittest.main()
