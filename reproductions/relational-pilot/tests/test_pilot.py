import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze
import annotations
import prepare
import prompts
import run
import scan


def view():
    return {"question": "What changed?", "pre_text": ["A is 50."],
            "post_text": [], "table": [["item", "year"], ["A", "50"]]}


def edit():
    return {"location": "pre_text/0", "start": 0, "end": 8, "original": "A is 50.",
            "replacement": "", "fact_description": "Delete disclosed A"}


class PreparationTests(unittest.TestCase):
    def test_freeze_transitive_family_report_isolation_and_test_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            v, deletion = view(), edit()
            changed = prepare.apply_edits(v, [deletion])
            registry_rows = [{"source_id": str(i), "family_id": f"f{i}", "report_id": f"r{i}"} for i in range(152)]
            registry_rows[150]["family_id"] = "f0"
            registry_rows[151]["report_id"] = "r150"
            universe = prepare.digest(sorted(r["source_id"] for r in registry_rows))
            drafts = []
            for i in range(150):
                reviews = []
                for reviewer in ("human_a", "human_b"):
                    review = {"reviewer": reviewer, "variant_sha256": prepare.digest(changed), "decision": "unanswerable"}
                    for flag in ("necessary_fact_removed", "equivalent_disclosures_checked", "alternative_formulas_checked", "alternative_paths_checked", "target_underdetermined", "question_preserved"):
                        review[flag] = True
                    for note in ("missing_fact", "equivalent_disclosure_audit", "alternative_path_audit", "underdetermination_reason", "reviewed_at"):
                        review[note] = "synthetic fixture only"
                    reviews.append(review)
                drafts.append({"source_id": str(i), "family_id": f"f{i}", "source_private": v,
                               "source_visible_sha256": prepare.digest(v), "visible": changed,
                               "variant_sha256": prepare.digest(changed), "edits_private": [deletion], "reviews": reviews})
            data = {"drafts": drafts, "provenance": {"split": "train"}, "complete_train_ids_sha256": universe}
            reg = {"sources": registry_rows, "reviewed_by": "synthetic fixture", "definition": "synthetic", "complete_train_ids_sha256": universe}
            selection = {"source_ids": [str(i) for i in range(150)], "approved_by": "synthetic fixture", "sampling_rule": "synthetic", "complete_train_ids_sha256": universe}
            for name, obj in (("data",data),("reg",reg),("selection",selection)):
                prepare.write_new(tmp/f"{name}.json",obj)
            prepare.freeze(tmp/"data.json",tmp/"reg.json",tmp/"selection.json",tmp/"frozen.json")
            self.assertEqual(len(prepare.read_json(tmp/"frozen.json")["exclude_from_future_training_and_formal_tests"]),152)
            data["protected_official_test_reports"] = ["r150"]
            prepare.write_new(tmp/"protected.json",data)
            with self.assertRaisesRegex(ValueError,"transitive"):
                prepare.freeze(tmp/"protected.json",tmp/"reg.json",tmp/"selection.json",tmp/"blocked.json")
            self.assertFalse((tmp/"blocked.json").exists())

    def test_exact_deletion_preserves_question_and_structure(self):
        original = view()
        changed = prepare.apply_edits(original, [edit()])
        self.assertEqual(changed["pre_text"], [""])
        self.assertEqual(changed["question"], original["question"])
        self.assertEqual(changed["table"], original["table"])
        self.assertEqual(original["pre_text"], ["A is 50."])

    def test_edit_drift_and_question_edits_rejected(self):
        bad = edit()
        bad["original"] = "A is 51."
        with self.assertRaisesRegex(ValueError, "drift"):
            prepare.apply_edits(view(), [bad])
        bad = edit()
        bad["location"] = "question"
        with self.assertRaises(ValueError):
            prepare.apply_edits(view(), [bad])

    def test_unreviewed_or_nonindependent_cannot_freeze(self):
        d = {"variant_sha256": "x", "reviews": []}
        with self.assertRaisesRegex(ValueError, "distinct"):
            prepare.validate_reviews(d)
        review = {"reviewer": "same"}
        d["reviews"] = [review, copy.deepcopy(review)]
        with self.assertRaisesRegex(ValueError, "distinct"):
            prepare.validate_reviews(d)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "artifact.json"
            prepare.write_new(p, {"v": 1})
            with self.assertRaises(FileExistsError):
                prepare.write_new(p, {"v": 2})
            self.assertEqual(prepare.read_json(p), {"v": 1})

    def test_zero_one_and_two_step_scan(self):
        v = {"question": "target", "pre_text": [], "post_text": [], "table": [["A", "B"], ["20", "3"], ["2", "7"]]}
        one = scan.alternate_paths(v, 23)
        self.assertTrue(any(w["steps"] == 1 for w in one["witnesses"]))
        two = scan.alternate_paths(v, 67)
        self.assertTrue(any(w["steps"] == 2 for w in two["witnesses"]))
        self.assertEqual(two["unit_and_semantic_validation"], "required_human_review")

    def test_formal_task_build_rejects_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"draft.json"
            prepare.write_new(p, {"status": "draft", "sources": []})
            with self.assertRaisesRegex(ValueError, "reviewed"):
                run.build_tasks(p, Path(tmp)/"tasks.json")


class PromptAndRuntimeTests(unittest.TestCase):
    def test_mock_api_and_resume_never_resends_or_writes_key(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self):
                return json.dumps({"model":"mock", "usage":{"total_tokens":10},"choices":[{"finish_reason":"stop","message":{"content":"insufficient evidence"}}]}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            providers, env = {}, {}
            for family in run.FAMILIES:
                providers[family] = {"endpoint_env":family+"_URL", "api_key_env":family+"_KEY", "model":"gpt-5-2025-08-07" if family=="gpt5" else "mock",
                                     "weights_id":"mock", "common_request":{"max_tokens":64,"n":1},
                                     "low_request":{"reasoning_effort":"minimal"} if family=="gpt5" else {"thinking":False},
                                     "high_request":{"reasoning_effort":"high"} if family=="gpt5" else {"thinking":True},
                                     "mode_verification":{"verified_by":"unit test mock","evidence":"mock only"}}
                env[family+"_URL"]="https://mock.invalid/chat/completions"
                env[family+"_KEY"]="mock-secret-never-log"
            prepare.write_new(tmp/"config.json",{"status":"ready","providers":providers})
            task = {"id":"t1","model_family":"gpt5","mode":"low","method":"cot_paired_4shot","messages":[{"role":"user","content":"mock question"}]}
            prepare.write_new(tmp/"tasks.json",{"status":"unit_test_fixture","tasks":[task]})
            with patch.dict(os.environ,env), patch("urllib.request.urlopen",return_value=Response()) as urlopen:
                run.run(tmp/"tasks.json",tmp/"config.json",tmp/"out",1,10)
                run.run(tmp/"tasks.json",tmp/"config.json",tmp/"out",1,10)
                self.assertEqual(urlopen.call_count,1)
            output = (tmp/"out/outputs.jsonl").read_text()
            self.assertNotIn("mock-secret-never-log",output)
            self.assertEqual(json.loads(output)["status"],"completed")

    def test_three_treatments_and_no_gold_leak(self):
        v = view()
        variants = {m: prompts.messages(m, v) for m in prompts.METHODS}
        self.assertEqual(len({json.dumps(m) for m in variants.values()}), 3)
        self.assertIn("If the evidence is insufficient", variants["cot_existing_abstention"][0]["content"])
        self.assertNotIn("If the evidence is insufficient", variants["cot_paired_4shot"][0]["content"])
        self.assertNotIn("#Python", variants["cot_paired_4shot"][0]["content"])
        self.assertEqual(len(prompts.demo_questions()), 4)
        self.assertIn("#Python", variants["pot"][-1]["content"])
        self.assertNotIn("gold_private", json.dumps(variants))

    def test_matrix_has_18_outputs_per_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, out = Path(tmp)/"d.json", Path(tmp)/"tasks.json"
            v = view()
            prepare.write_new(p, {"drafts": [{"source_id": "s", "family_id": None, "visible": v, "variant_sha256": prepare.digest(v)}]})
            run.build_tasks(p, out, exploratory=True)
            task_bundle = prepare.read_json(out)
            self.assertEqual(task_bundle["task_count"], 18)
            self.assertEqual(len({t["id"] for t in task_bundle["tasks"]}), 18)
            self.assertEqual(sum(t["comparison"] == "core" for t in task_bundle["tasks"]), 12)

    def test_null_budget_fails_without_calling_api(self):
        c = prepare.read_json(Path(__file__).resolve().parents[1]/"providers.example.json")
        with patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(ValueError):
                run.validate_config(c)
            urlopen.assert_not_called()

    def test_truncation_and_unknown_not_completed(self):
        for finish, expected in (("length", "truncated"), ("content_filter", "unknown"), ("stop", "completed")):
            raw = {"choices": [{"message": {"content": "42"}, "finish_reason": finish}]}
            self.assertEqual(run.parse_response(raw)[1], expected)


class AnnotationStatisticsTests(unittest.TestCase):
    def test_blind_export_and_independent_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            v = view()
            task = {"id":"task1", "source_id":"source1", "family_id":"f1", "model_family":"gpt5", "method":"pot", "mode":"high", "variant_sha256":prepare.digest(v)}
            prepare.write_new(tmp/"data.json",{"sources":[{"source_id":"source1","visible":v,"variant_sha256":prepare.digest(v),"gold_private":{"answer":"SECRET_GOLD"}}]})
            prepare.write_new(tmp/"tasks.json",{"status":"unit_test_fixture","tasks":[task]})
            (tmp/"outputs.jsonl").write_text(json.dumps({"id":"task1","status":"completed","content":"42"})+"\n")
            annotations.export(tmp/"data.json",tmp/"tasks.json",tmp/"outputs.jsonl",tmp/"blind","mock-seed")
            a=prepare.read_json(tmp/"blind/reviewer_A.json")
            public_text=json.dumps(a)
            for hidden in ("SECRET_GOLD", "model_family", '"method"', '"mode"'):
                self.assertNotIn(hidden,public_text)
            a["reviewer"]="reviewer-a"
            for item in a["items"]:
                item.update(response_type="answer",rationale="synthetic annotation")
                item["labels"]=dict.fromkeys(annotations.LABELS,False)
                item["labels"]["wrong_answer"]=True
            b=copy.deepcopy(a);b["reviewer"]="reviewer-b"
            prepare.write_new(tmp/"a.json",a);prepare.write_new(tmp/"b.json",b)
            annotations.merge(tmp/"a.json",tmp/"b.json",tmp/"blind/private_key.json",None,tmp/"merged.json")
            self.assertEqual(prepare.read_json(tmp/"merged.json")["status"],"adjudicated")
            b["items"][0]["labels"]["relational_hallucination"]=True
            prepare.write_new(tmp/"b-disagree.json",b)
            annotations.merge(tmp/"a.json",tmp/"b-disagree.json",tmp/"blind/private_key.json",None,tmp/"dispute.json")
            self.assertEqual(prepare.read_json(tmp/"dispute.json")["status"],"awaiting_adjudication")

    def row(self, family="f1", status="completed", **labels):
        lab = dict.fromkeys(annotations.LABELS, False)
        lab.update(labels)
        return {"task": {"family_id": family, "source_id": family}, "status": status,
                "annotation": {"response_type": "answer", "labels": lab}}

    def test_dual_policies_preserve_mixed_error(self):
        r = self.row(wrong_answer=True, outside_document_input_number=True,
                     numeric_hallucination=True, relational_hallucination=True)
        exclusive = analyze.flags(r, "numeric_provenance_exclusive")
        independent = analyze.flags(r, "independent_overlapping")
        self.assertEqual((exclusive["numeric"], exclusive["relation"]), (1,0))
        self.assertEqual((independent["numeric"], independent["relation"]), (1,1))

    def test_failures_retained_not_correct_refusal(self):
        rows = [self.row(wrong_answer=True, relational_hallucination=True),
                self.row("f2", status="execution_failed", correct_refusal=True)]
        metric = analyze.metrics(rows, "independent_overlapping")
        self.assertEqual(metric["n_all_unanswerable"], 2)
        self.assertEqual(metric["relation_rate"], .5)
        self.assertEqual(metric["unfinished_rate"], .5)
        self.assertEqual(metric["correct_refusal_rate"], 0)

    def test_bootstrap_preserves_family_cluster(self):
        rows = [self.row("f1"), self.row("f1"), self.row("f2")]
        for sample in analyze.resamples(rows, seed=5, replicates=20):
            self.assertEqual(sum(r["task"]["family_id"] == "f1" for r in sample) % 2, 0)

    def test_zero_ratio_and_undefined_kappa(self):
        a = [self.row("f1")]
        b = [self.row("f1", wrong_answer=True, relational_hallucination=True)]
        # Exercise comparisons with short bootstrap in tests only.
        original = analyze.resamples
        with patch.object(analyze, "resamples", side_effect=lambda rows, seed: original(rows, seed, 20)):
            result = analyze.compare(a, b, "independent_overlapping", 1)
        self.assertNotIn("relation_rate_ratio", result)
        self.assertEqual(result["relation_rate_difference"]["estimate"], 1)
        x = [{"labels": {"x": False}}]
        self.assertIsNone(annotations.agreement(x, x, "x")["kappa"])

    def test_partial_annotation_not_valid(self):
        with self.assertRaises(ValueError):
            annotations.validate_item({"response_type": "answer", "labels": {}})


if __name__ == "__main__":
    unittest.main()
