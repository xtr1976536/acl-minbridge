"""Prepare a test-report-disjoint review batch before the final family audit."""
import argparse
import copy

from candidates import norm
from prepare import digest, load_finqa, read_json, report_group, write_new


def isolate(queue_path, index_path, test_path, batch_output, audit_output, family_output, count):
    queue, index, test = read_json(queue_path), read_json(index_path), load_finqa(test_path)
    protected_reports = {report_group(r) for r in test} - {None}
    test_questions = {norm(r["qa"]["question"]) for r in test}
    pool, skipped = [], []
    for row in queue["drafts"]:
        if row["source_report_provisional"] in protected_reports:
            skipped.append({"source_id": row["source_id"], "reason": "same_report_as_official_test"})
        elif norm(row["visible"]["question"]) in test_questions:
            skipped.append({"source_id": row["source_id"], "reason": "same_question_as_official_test"})
        else:
            pool.append(row)
    # Spread the initial review workload across reports, not a final sampling rule.
    batch, seen_reports = [], set()
    for row in pool:
        report = row["source_report_provisional"]
        if report and report not in seen_reports:
            batch.append(row)
            seen_reports.add(report)
        if len(batch) == count:
            break
    if len(batch) != count:
        raise ValueError("Not enough report-disjoint draft candidates")
    output = copy.deepcopy(queue)
    output.update(status="test_report_disjoint_draft_batch_requires_family_and_answerability_review",
                  drafts=batch, batch_count=count,
                  protected_official_test_reports=sorted(protected_reports),
                  selection_note="Initial review workload: first candidate from each distinct report in the hash-ordered test-report-disjoint draft pool. This is not the final 150-source sample or a representative-sampling claim.")
    write_new(batch_output, output)
    train_reports = {s["source_report_provisional"] for s in index["sources"]} - {None}
    write_new(audit_output, {"train_source_count": index["source_count"], "test_source_count": len(test),
                             "train_report_count": len(train_reports), "test_report_count": len(protected_reports),
                             "shared_report_count": len(train_reports & protected_reports),
                             "shared_reports": sorted(train_reports & protected_reports),
                             "candidate_pool_after_known_test_exclusion": len(pool),
                             "review_batch_size": count, "review_batch_distinct_reports": len(seen_reports),
                             "review_batch_test_report_overlap": sorted(seen_reports & protected_reports),
                             "pending": "Semantic families and cross-dataset duplicates still require review",
                             "skipped_candidates": skipped})
    write_new(family_output, {"reviewed_by": None, "definition": None,
                              "complete_train_ids_sha256": index["complete_train_ids_sha256"],
                              "sources": [{"source_id": s["source_id"], "family_id": None,
                                           "report_id": s["source_report_provisional"]} for s in index["sources"]]})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("queue", "index", "test", "batch-output", "audit-output", "family-output"):
        p.add_argument("--"+arg, required=True)
    p.add_argument("--count", type=int, required=True)
    a = p.parse_args()
    isolate(a.queue, a.index, a.test, a.batch_output, a.audit_output, a.family_output, a.count)
