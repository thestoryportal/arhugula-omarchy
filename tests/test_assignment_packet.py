"""Assignment packets carry complete current context as bounded verified pointers."""
from dataclasses import fields, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ops.orchestration.assignment_packet import (
    PROJECTION_LIMIT,
    SLICE_LIMIT,
    ArtifactIndex,
    Assignment,
    Finding,
    Guidance,
    admit_recipient,
    adoption_body,
    assemble,
    build_packet,
    index_artifact,
    read_slice,
)
from ops.orchestration.communication import Hold, Reason, Recipient, VerifiedComment, ensure_comment
from ops.orchestration.startup import StartupBudgetRejected, budget


UNIT = "trial-193.u9f.p1s"
WORKER = "01a16b50-5b2b-7260-9e8e-8dd62d4398d2"
BASELINE = "2676226d87bdfb0cb7cba97522a0ee8f7254949d"
STALE = "01a16b2a-9b5c-7533-88eb-fe4266fe75a4"


class FakeLit:
    """LIT seam: an append-only comment store."""

    def __init__(self):
        self.comments = []

    def export(self):
        return {"comments": [dict(c) for c in self.comments]}

    def comment(self, issue, body):
        self.comments.append({"id": f"cmt-{len(self.comments) + 1:04d}", "issue_id": issue, "body": body})


def _record(kind, payload):
    return {"timestamp": "2026-10-24T00:00:00Z", "type": kind, "payload": payload}


def transcript(session=WORKER, *, model="gpt-test", effort="medium", inputs=100,
               output=10, measured=True, complete=True, compacted=False):
    """One native Codex turn; each keyword is a single native fact a case can break."""
    records = [
        _record("session_meta", {"id": session}),
        _record("turn_context", {"model": model, "effort": effort}),
        _record("event_msg", {"type": "task_started", "turn_id": "t1", "model_context_window": 1000}),
    ]
    if measured:
        usage = {"input_tokens": inputs, "cached_input_tokens": 0, "output_tokens": output}
        records.append(_record("event_msg", {"type": "token_count", "info": {
            "last_token_usage": usage, "model_context_window": 1000}}))
    if compacted:
        records.append(_record("event_msg", {"type": "context_compacted"}))
    if complete:
        records.append(_record("event_msg", {"type": "task_complete", "turn_id": "t1"}))
    return "".join(json.dumps(record) + "\n" for record in records)


class Fixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.transcript = self.root / "rollout.jsonl"
        self.transcript.write_text(transcript())
        self.routing = self.root / "session-control.json"
        self.control = {"version": 1, "repair_paused": False, "ticket": "trial-193", "sessions": [
            {"role": "implementer", "kind": "codex", "session_id": WORKER,
             "transcript": str(self.transcript), "ceiling": 1000, "reserve": 100, "task_budget": 200}]}
        self.routing.write_text(json.dumps(self.control))
        self.profiles = self.root / "launch-profiles.json"
        self.profiles.write_text(json.dumps({"version": 1, "roles": {"implementer": {
            "client": "codex", "model": "gpt-test", "effort": "medium", "role_file": "implementer.md"}}}))
        self.recipient = Recipient("implementer", "independent reviewer", WORKER)
        # The startup receipt is measured once, when the session finishes startup.
        self.startup = budget(self.transcript, WORKER)
        self.lit = FakeLit()
        self.role = self.root / "implementer.md"
        self.role.write_text("reviewer role\n")
        self.laws = self.root / "code-SKILL.md"
        self.laws.write_text("code laws\n")
        self.guidance = (Guidance(str(self.role), "startup"), Guidance(str(self.laws), "code"))
        self.pointer = self.publish(UNIT, "assign", "TO implementer: review U13 at abc123.")

    def publish(self, issue, operation, body):
        return ensure_comment(self.lit, issue, f"wo-u13-{operation}", body, ledger=self.root / "ledger")

    def adopt(self, *paths, session=WORKER, compactions=0):
        """The session's own adoption record of the current bytes of ``paths``."""
        sources = {(str(path), hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths}
        return self.publish(UNIT, f"adopt-{len(self.lit.comments)}", adoption_body(session, compactions, sources))

    def admitted(self, *, ceiling=1000, adoption=None, **changes):
        return admit_recipient(
            changes.get("recipient", self.recipient), routing=self.routing, profiles=self.profiles,
            ceiling=ceiling, startup=changes.get("startup", self.startup), adoption=adoption, lit=self.lit)

    def artifact(self, name, data, *supersedes, purpose="design"):
        path = self.root / name
        path.write_bytes(data)
        return index_artifact(path, producer="claude-coder", purpose=purpose,
                              policy_version="wo-v1", supersedes=tuple(a.sha256 for a in supersedes))

    def assignment(self, **changes):
        values = dict(
            goal="Ground admitted workers with complete bounded current artifacts",
            unit=UNIT, pointer=self.pointer, recipient=self.admitted(), baseline=BASELINE,
            owned=("ops/orchestration/assignment_packet.py",), deliverables=("assignment packet module",),
            acceptance=("WT-04", "WT-05"), constraints=("no ceiling or watcher change",),
            guidance=self.guidance, findings=(), verification=("python -m unittest tests.test_assignment_packet",),
            evidence="docs/orchestration/implementation-evidence/wo-u13", dependencies=("trial-193.u9f.z9o",),
            stop="packet and admission behavior only")
        return Assignment(**{**values, **changes})

    def packet(self, assignment=None, artifacts=()):
        return build_packet(assignment or self.assignment(), ArtifactIndex(tuple(artifacts)), lit=self.lit)


class AdmissionTests(Fixture):
    def test_idle_matched_worker_is_admitted_with_measured_capacity(self):
        admitted = self.admitted()
        self.assertEqual(admitted.recipient, self.recipient)
        self.assertEqual((admitted.model, admitted.effort), ("gpt-test", "medium"))
        self.assertEqual(admitted.capacity["decision"], "allow")
        self.assertEqual(admitted.capacity["remaining_tokens"], 900)
        self.assertEqual(admitted.startup["limit_percent"], 15)

    def test_only_a_measured_eligible_session_is_admitted(self):
        over_cap = self.root / "over-cap.jsonl"
        over_cap.write_text(transcript(inputs=150, output=1))
        with self.assertRaises(StartupBudgetRejected) as rejected:
            budget(over_cap, WORKER)
        cases = [
            ("wrong uuid", dict(recipient=Recipient("implementer", "reviewer", STALE)), None, Reason.IDENTITY_MISMATCH),
            ("transcript of another session", {}, transcript(session=STALE), Reason.IDENTITY_MISMATCH),
            ("substituted model", {}, transcript(model="gpt-other"), Reason.IDENTITY_MISMATCH),
            ("substituted effort", {}, transcript(effort="high"), Reason.IDENTITY_MISMATCH),
            ("active writer", {}, transcript(complete=False), Reason.OWNERSHIP_CONFLICT),
            ("missing native capacity", {}, transcript(measured=False), Reason.HEADROOM_UNKNOWN),
            ("insufficient headroom", {}, transcript(inputs=800), Reason.REFRESH_REQUIRED),
            ("ceiling differs from effective", dict(ceiling=900), None, Reason.POLICY_MISMATCH),
            ("startup over the 15-percent cap", dict(startup=rejected.exception.report), None, Reason.REFRESH_REQUIRED),
            ("startup receipt of another session", dict(startup={**self.startup, "session_id": STALE}), None, Reason.IDENTITY_MISMATCH),
            ("startup receipt without measurements", dict(startup={"session_id": WORKER}), None, Reason.HEADROOM_UNKNOWN),
            ("startup receipt with an inconsistent limit", dict(startup={**self.startup, "limit_tokens": 999}), None, Reason.HEADROOM_UNKNOWN),
            ("startup receipt from another window", dict(startup={**self.startup, "context_window_tokens": 2000, "limit_tokens": 300}), None, Reason.HEADROOM_UNKNOWN),
            ("adoption of another session", dict(adoption=self.adopt(self.role, session=STALE)), None, Reason.IDENTITY_MISMATCH),
            ("adoption never stored in LIT", dict(adoption=VerifiedComment(UNIT, "cmt-none", "f" * 64, "wo-u13-adopt-none")), None, Reason.INVALID_INPUT),
        ]
        for name, changes, native, reason in cases:
            with self.subTest(name):
                self.transcript.write_text(native or transcript())
                with self.assertRaises(Hold) as held:
                    self.admitted(**changes)
                self.assertEqual(held.exception.reason, reason)

    def test_pause_refuses_admission(self):
        self.routing.write_text(json.dumps({**self.control, "repair_paused": True}))
        with self.assertRaises(Hold) as held:
            self.admitted()
        self.assertEqual(held.exception.reason, Reason.AUTHORITY_CHANGED)

    def test_full_guidance_is_read_once_per_unchanged_source(self):
        before = (self.routing.read_bytes(), self.profiles.read_bytes())
        role, laws = self.guidance
        first = self.packet()
        self.assertEqual([s.path for s in first.reads], [role.path, laws.path])
        # The worker publishes its adoption; the next related unit arrives by
        # pointer with no introduction or repeated Law read.
        adopted = self.admitted(adoption=self.adopt(self.role, self.laws))
        next_unit = "trial-193.u9f.ct8"
        second = self.packet(self.assignment(unit=next_unit, recipient=adopted,
                                             pointer=self.publish(next_unit, "assign-ct8", "TO implementer: U14.")))
        self.assertEqual(second.reads, ())
        self.assertEqual([g["loaded"] for g in json.loads(second.text)["guidance"]], [True, True])
        # A source edited after adoption is read again from its current bytes.
        self.laws.write_text("code laws, amended\n")
        changed = self.packet(self.assignment(recipient=adopted))
        self.assertEqual([(s.path, s.sha256) for s in changed.reads],
                         [(laws.path, hashlib.sha256(self.laws.read_bytes()).hexdigest())])
        self.assertEqual([g["loaded"] for g in json.loads(changed.text)["guidance"]], [True, False])
        # Compaction since adoption may have dropped any source from context.
        self.transcript.write_text(transcript(compacted=True))
        compacted = self.admitted(adoption=self.adopt(self.role, self.laws))
        self.assertEqual(len(self.packet(self.assignment(recipient=compacted)).reads), 2)
        self.assertEqual((self.routing.read_bytes(), self.profiles.read_bytes()), before)


class PacketTests(Fixture):
    def test_missing_required_context_refuses_dispatch(self):
        optional = {"findings", "dependencies"}
        for field in fields(Assignment):
            if field.name in optional or field.name in {"pointer", "recipient"}:
                continue
            with self.subTest(field.name):
                empty = "" if isinstance(getattr(self.assignment(), field.name), str) else ()
                with self.assertRaises(Hold) as held:
                    self.assignment(**{field.name: empty})
                self.assertEqual(held.exception.reason, Reason.INVALID_INPUT)
                self.assertIn(field.name, str(held.exception))
        for name, changes in (("short baseline", dict(baseline=BASELINE[:7])),
                              ("pointer on another unit", dict(pointer=replace(self.pointer, issue="trial-193.u9f.ct8")))):
            with self.subTest(name), self.assertRaises(Hold):
                self.assignment(**changes)

    def test_pointer_must_be_the_stored_lit_comment(self):
        for name, pointer in (
            ("absent comment", VerifiedComment(UNIT, "cmt-does-not-exist", "f" * 64, "wo-u13-assign")),
            ("altered body hash", replace(self.pointer, body_sha256="f" * 64)),
            ("another operation", replace(self.pointer, operation_id="wo-u13-other")),
        ):
            with self.subTest(name), self.assertRaises(Hold) as held:
                self.packet(self.assignment(pointer=pointer))
            self.assertEqual(held.exception.reason, Reason.INVALID_INPUT)

    def test_packet_retains_all_material_findings(self):
        plan = self.artifact("plan-v1.md", b"plan v1\n")
        amendment = self.artifact("amendment-1.md", b"amend section 2\n", plan)
        effective = self.artifact("plan-effective.md", b"plan v1 with section 2 amended\n", amendment)
        findings = (
            Finding(UNIT, "cmt-f1", plan.sha256, None),
            Finding(UNIT, "cmt-f2", amendment.sha256, "cmt-f2-fix"),
            Finding(UNIT, "cmt-f3", effective.sha256, None),
        )
        packet = self.packet(self.assignment(findings=findings), (plan, amendment, effective))
        projected = json.loads(packet.text)
        self.assertEqual(projected["views"], [{"document": effective.sha256,
                                               "lineage": [plan.sha256, amendment.sha256, effective.sha256]}])
        # The finding raised against the superseded plan stays visible and retrievable.
        self.assertEqual([(f["comment_id"], f["against"], f["resolved_by"]) for f in projected["findings"]],
                         [("cmt-f1", plan.sha256, None), ("cmt-f2", amendment.sha256, "cmt-f2-fix"),
                          ("cmt-f3", effective.sha256, None)])
        with self.assertRaises(Hold) as held:
            self.packet(self.assignment(findings=(Finding(UNIT, "cmt-f4", "d" * 64, None),)), (plan,))
        self.assertIn("cmt-f4", str(held.exception))

    def test_conflicting_amendments_refuse_effective_view(self):
        plan = self.artifact("plan.md", b"original plan\n")
        first = self.artifact("amend-a.md", b"section 2 says A\n", plan)
        second = self.artifact("amend-b.md", b"section 2 says B\n", plan)
        with self.assertRaises(Hold) as held:
            self.packet(artifacts=(plan, first, second))
        self.assertEqual(held.exception.reason, Reason.OWNERSHIP_CONFLICT)
        self.assertIn(first.sha256, str(held.exception))
        self.assertIn(second.sha256, str(held.exception))
        merged = self.artifact("plan-effective.md", b"original plan, section 2 resolved\n", first, second)
        packet = self.packet(artifacts=(plan, first, second, merged))
        self.assertEqual([v.lineage for v in packet.views],
                         [(plan.sha256, first.sha256, second.sha256, merged.sha256)])
        self.assertEqual(hashlib.sha256((self.root / "plan.md").read_bytes()).hexdigest(), plan.sha256)

    def test_lineage_is_append_only(self):
        plan = self.artifact("plan.md", b"original plan\n")
        amendment = self.artifact("amend.md", b"amend\n", plan)
        for name, artifacts in (("parent after child", (amendment, plan)), ("duplicate", (plan, plan))):
            with self.subTest(name), self.assertRaises(Hold) as held:
                ArtifactIndex(artifacts)
            self.assertEqual(held.exception.reason, Reason.INVALID_INPUT)

    def test_large_result_requires_complete_slices(self):
        data = b"".join(b'{"id": "cmt-%06d", "body": "finding text"}\n' % n for n in range(3000))
        export = self.artifact("lit-export.json", data, purpose="selected result")
        self.assertGreater(export.byte_length, 4 * SLICE_LIMIT)
        packet = self.packet(artifacts=(export,))
        self.assertLessEqual(len(packet.text.encode()), PROJECTION_LIMIT)
        self.assertNotIn("finding text", packet.text)
        slices = []
        while sum(len(s.data) for s in slices) < export.byte_length:
            slices.append(read_slice(export, sum(len(s.data) for s in slices)))
        self.assertTrue(all(len(s.data) <= SLICE_LIMIT for s in slices))
        self.assertEqual(assemble(export, slices), data)
        for name, partial in (("truncated", slices[:-1]), ("gap", slices[:1] + slices[2:])):
            with self.subTest(name), self.assertRaises(Hold) as held:
                assemble(export, partial)
            self.assertEqual(held.exception.reason, Reason.INVALID_INPUT)
        with self.assertRaises(Hold):
            read_slice(export, 0, SLICE_LIMIT + 1)
        (self.root / "lit-export.json").write_bytes(data.replace(b"finding", b"FINDING", 1))
        changed = [read_slice(export, s.offset) for s in slices]
        with self.assertRaises(Hold) as held:
            assemble(export, changed)
        self.assertEqual(held.exception.reason, Reason.ARTIFACT_UNAVAILABLE)

    def test_oversized_projection_refuses_instead_of_truncating(self):
        with self.assertRaises(Hold) as held:
            self.packet(self.assignment(deliverables=("x" * PROJECTION_LIMIT,)))
        self.assertEqual(held.exception.reason, Reason.INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
