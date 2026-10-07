"""GI-Gemma provisional structural validators, synthetic-preparation scope only.

No transcript loading, anonymization, label inference, model calls or gold promotion.
All semantic choices remain subject to the source schema/codebook review.
"""
from __future__ import annotations
import copy
import json
import math
from dataclasses import asdict, dataclass

VERSION = "gigemma-canonical-candidate-v0.1"
DA = frozenset("question answer proposal agreement disagreement elaboration clarification example topic_shift other".split())
STANCE = frozenset("support oppose neutral mixed unclear".split())
RELATION = frozenset("reply_to support contradict elaborate question answer unrelated".split())
REQUIRED = ("session_id", "source_revision", "turn_id", "speaker_id", "text", "start_ms", "end_ms", "asr_confidence")


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    location: str
    message: str


def number(value):
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def key(row):
    return tuple(row.get(k) for k in ("session_id", "source_revision", "turn_id"))


def report(issues, count):
    errors = sum(x.severity == "error" for x in issues)
    warnings = sum(x.severity == "warning" for x in issues)
    return {"validator_version": VERSION, "schema_status": "proposed_not_approved",
            "rows_checked": count, "error_count": errors, "warning_count": warnings,
            "status": "invalid" if errors else "review_required" if warnings else "structurally_valid_candidate",
            "semantic_accuracy_measured": False, "gold_promoted": False,
            "issues": [asdict(x) for x in issues]}


def validate_canonical(rows, *, expected_order=None, asr_metadata=None):
    """Validate an already supplied row list without editing, dropping or sorting rows.

    Required fields and confidence metadata are a reviewable candidate profile.
    Timestamps accept finite int/float milliseconds; null is preserved. Overlap is
    permitted. A trusted source-order list is optional and must be provided by the
    caller to detect a reordered input. Speaker IDs are never linked across sessions.
    """
    issues = []
    add = lambda severity, code, loc, message: issues.append(Issue(severity, code, loc, message))
    if not isinstance(rows, list):
        add("error", "rows_type", "$", "Expected a list of canonical rows")
        return report(issues, 0)
    if not rows:
        add("warning", "empty_dataset", "rows", "No rows supplied; not an evaluation-ready dataset")
    seen, revisions, actual_order = set(), {}, []
    for i, row in enumerate(rows):
        loc = f"rows[{i}]"
        if not isinstance(row, dict):
            add("error", "row_type", loc, "Expected an object")
            continue
        for field in REQUIRED:
            if field not in row:
                add("error", "missing_field", loc + "." + field, "Missing candidate-profile field; do not infer a value")
        id_ok = True
        for field in ("session_id", "source_revision", "turn_id"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                add("error", "invalid_id", loc + "." + field, "Expected a nonempty string ID")
                id_ok = False
        if id_ok:
            k = key(row)
            actual_order.append(k)
            if k in seen:
                add("error", "duplicate_turn", loc, "Duplicate session/revision/turn key")
            seen.add(k)
            revisions.setdefault(row["session_id"], set()).add(row["source_revision"])
        speaker = row.get("speaker_id")
        if speaker is None:
            add("warning", "speaker_unknown", loc + ".speaker_id", "Unknown speaker retained; no identity grouping inferred")
        elif not isinstance(speaker, str) or not speaker.strip():
            add("error", "speaker_type", loc + ".speaker_id", "Expected a nonempty anonymous ID or null")
        if not isinstance(row.get("text"), str):
            add("error", "text_type", loc + ".text", "Text must be a string")
        elif not row["text"]:
            add("warning", "text_empty", loc + ".text", "Empty text retained for review, not silently discarded")
        for field in ("start_ms", "end_ms"):
            value = row.get(field)
            if value is not None and (not number(value) or value < 0):
                add("error", "timestamp_type", loc + "." + field, "Timestamp must be finite nonnegative milliseconds or null")
        start, end = row.get("start_ms"), row.get("end_ms")
        if number(start) and number(end) and start > end:
            add("error", "timestamp_order", loc, "start_ms exceeds end_ms")
        if (start is None) != (end is None):
            add("warning", "timestamp_partial", loc, "One provided timestamp retained; missing endpoint not synthesized")
        confidence = row.get("asr_confidence")
        if confidence is not None:
            if not number(confidence):
                add("error", "asr_type", loc + ".asr_confidence", "Confidence must be finite numeric or null")
            elif not isinstance(asr_metadata, dict) or not asr_metadata.get("source") or not asr_metadata.get("scale"):
                add("warning", "asr_provenance_missing", loc + ".asr_confidence", "Provided score needs scale and source before interpretation")
            elif "range" in asr_metadata:
                bounds = asr_metadata["range"]
                if not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or not all(number(v) for v in bounds) or bounds[0] > bounds[1]:
                    add("error", "asr_metadata_range", "asr_metadata.range", "Invalid declared score range")
                elif not bounds[0] <= confidence <= bounds[1]:
                    add("error", "asr_out_of_range", loc + ".asr_confidence", "Score lies outside its explicitly declared range")
    for session, versions in revisions.items():
        if len(versions) > 1:
            add("warning", "multiple_revisions", "rows", "A session has multiple source revisions; select the annotation source explicitly")
    if expected_order is not None:
        reference = [tuple(v) for v in expected_order]
        if actual_order != reference:
            add("error", "source_order_mismatch", "rows", "Row IDs/order differ from supplied source-order reference")
    result = report(issues, len(rows))
    result["source_order_checked"] = expected_order is not None
    result["input_rows_modified"] = False
    return result


def _object_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON object key")
        result[name] = value
    return result


def strict_json_loads(text):
    def invalid_constant(_):
        raise ValueError("Non-finite JSON constant")
    return json.loads(text, object_pairs_hook=_object_pairs, parse_constant=invalid_constant)


def encode_jsonl(rows):
    """Lossless serialization. Does not anonymize, normalize, impute or filter."""
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows)


def decode_jsonl(text):
    rows = []
    if not isinstance(text, str):
        raise ValueError("JSONL input must be text")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    for index, line in enumerate(lines):
        if not line.strip():
            raise ValueError(f"Blank JSONL record at line {index + 1}")
        row = strict_json_loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Non-object JSONL record at line {index + 1}")
        rows.append(row)
    return rows


def validate_windows(windows, rows):
    issues, seen = [], set()
    if not isinstance(windows, list):
        return report([Issue("error", "windows_type", "windows", "Expected a window list")], 0)
    add = lambda code, i, msg: issues.append(Issue("error", code, f"windows[{i}]", msg))
    groups = {}
    for row in rows:
        groups.setdefault((row["session_id"], row["source_revision"]), []).append(row["turn_id"])
    for i, w in enumerate(windows):
        if not isinstance(w, dict):
            add("window_type", i, "Window must be an object")
            continue
        wid = w.get("window_id")
        if not isinstance(wid, str) or not wid or wid in seen:
            add("window_id", i, "Window ID missing or duplicated")
        seen.add(wid if isinstance(wid, str) else None)
        group = (w.get("session_id"), w.get("source_revision"))
        if not all(isinstance(value, str) and value for value in group):
            add("window_group_type", i, "session/revision IDs must be nonempty strings")
            continue
        turns = w.get("turn_ids")
        if not isinstance(turns, list) or not all(isinstance(t, str) for t in turns):
            add("window_turn_type", i, "turn_ids must be a string list")
            continue
        if len(turns) != len(set(turns)):
            add("window_turn_duplicate", i, "Window repeats an original turn")
        known = groups.get(group, [])
        if any(t not in known for t in turns):
            add("window_cross_reference", i, "Window references another session/revision or an unknown turn")
        else:
            positions = [known.index(t) for t in turns]
            if positions != sorted(positions):
                add("window_order", i, "Window changes source turn order")
    return report(issues, len(windows))


def validate_splits(assignments, rows, *, require_independent_eval=False):
    """All revisions/windows of one session stay grouped; no split is generated."""
    issues, by_session, assigned = [], {}, set()
    if not isinstance(assignments, list):
        return report([Issue("error", "assignments_type", "assignments", "Expected an assignment list")], 0)
    known = {(r["session_id"], r["source_revision"]) for r in rows}
    for i, a in enumerate(assignments):
        loc = f"assignments[{i}]"
        if not isinstance(a, dict):
            issues.append(Issue("error", "split_type", loc, "Assignment must be an object")); continue
        group = (a.get("session_id"), a.get("source_revision"))
        split = a.get("split")
        if not all(isinstance(value, str) and value for value in group) or not isinstance(split, str):
            issues.append(Issue("error", "split_field_type", loc, "Session, revision and split must be strings")); continue
        if group not in known:
            issues.append(Issue("error", "split_unknown_group", loc, "Unknown session/revision"))
        if group in assigned:
            issues.append(Issue("error", "split_duplicate_group", loc, "Group assigned more than once"))
        assigned.add(group)
        if split not in {"train", "dev", "test"}:
            issues.append(Issue("error", "split_label", loc, "Expected train, dev or test"))
        by_session.setdefault(group[0], set()).add(split)
    if assigned != known:
        issues.append(Issue("error", "split_coverage", "assignments", "Assignments must cover exactly the observed session/revision groups"))
    if any(len(values) > 1 for values in by_session.values()):
        issues.append(Issue("error", "session_leakage", "assignments", "A session crosses splits, including different source revisions"))
    splits_present = {a.get("split") for a in assignments if isinstance(a, dict) and isinstance(a.get("split"), str)}
    if require_independent_eval and (splits_present != {"train", "dev", "test"} or len(by_session) < 3):
        issues.append(Issue("error", "independent_eval_unavailable", "assignments", "Separate train/dev/test sessions are not present; no independence claim permitted"))
    return report(issues, len(assignments))


def validate_evidence(evidence, rows, *, session_id, source_revision, offset_policy):
    issues = []
    if not isinstance(evidence, list):
        return report([Issue("error", "evidence_list_type", "evidence", "Expected an evidence list")], 0)
    lookup = {key(row): row for row in rows}
    if offset_policy != "unicode_codepoints_half_open_proposal_v0":
        return report([Issue("error", "offset_policy", "offset_policy", "Explicit candidate Unicode/codepoint/half-open policy required")], len(evidence))
    for i, item in enumerate(evidence):
        loc = f"evidence[{i}]"
        if not isinstance(item, dict):
            issues.append(Issue("error", "evidence_type", loc, "Evidence must be an object")); continue
        revision = item.get("source_revision", source_revision)
        if not isinstance(revision, str) or not isinstance(item.get("turn_id"), str):
            issues.append(Issue("error", "evidence_reference_type", loc, "Revision and turn IDs must be strings")); continue
        target = lookup.get((session_id, revision, item.get("turn_id")))
        if revision != source_revision or target is None:
            issues.append(Issue("error", "evidence_reference", loc, "Evidence references another revision/session or unknown turn")); continue
        span = item.get("text_span")
        if not isinstance(span, dict):
            issues.append(Issue("error", "span_type", loc, "text_span must be an object")); continue
        start, end, quote = span.get("start_char"), span.get("end_char"), span.get("quote")
        if type(start) is not int or type(end) is not int or not isinstance(quote, str) or not 0 <= start < end <= len(target["text"]):
            issues.append(Issue("error", "span_bounds", loc, "Invalid nonempty codepoint span"))
        elif target["text"][start:end] != quote:
            issues.append(Issue("error", "quote_mismatch", loc, "Quote does not exactly match the source span; normalization is not applied"))
    return report(issues, len(evidence))


def validate_ir_references(records, rows):
    """Reference and candidate-label checks, not meaning or gold validation.

    Object/list stance/relation are both inspected, never silently converted.
    Their final cardinality remains a human decision.
    """
    if not isinstance(records, list):
        return report([Issue("error", "ir_list_type", "records", "Expected an IR list")], 0)
    issues, lookup = [], {key(row): row for row in rows}
    for i, record in enumerate(records):
        loc = f"records[{i}]"
        if not isinstance(record, dict):
            issues.append(Issue("error", "ir_type", loc, "IR must be an object")); continue
        if not all(isinstance(record.get(name), str) and record.get(name) for name in ("session_id", "source_revision", "turn_id")):
            issues.append(Issue("error", "ir_reference_type", loc, "IR IDs must be nonempty strings")); continue
        target = lookup.get(key(record))
        if target is None:
            issues.append(Issue("error", "ir_reference", loc, "IR key is absent from input")); continue
        if record.get("speaker_id") != target["speaker_id"]:
            issues.append(Issue("error", "speaker_reference", loc, "IR speaker differs from canonical input"))
        acts = record.get("dialogue_act", [])
        if not isinstance(acts, list) or any(not isinstance(x, str) or x not in DA for x in acts):
            issues.append(Issue("error", "da_label", loc, "DA not in the unchanged candidate vocabulary"))
        for field, vocabulary in (("stance", STANCE), ("relation", RELATION)):
            value = record.get(field)
            values = value if isinstance(value, list) else [] if value is None else [value]
            for j, item in enumerate(values):
                if not isinstance(item, dict):
                    issues.append(Issue("error", field + "_type", loc, "Expected object, list of objects or null")); continue
                label = item.get("label" if field == "stance" else "type")
                if not isinstance(label, str) or label not in vocabulary:
                    issues.append(Issue("error", field + "_label", loc, "Label not in candidate vocabulary"))
                if field == "stance" and ("target" not in item or item["target"] in (None, "", {}, [])):
                    issues.append(Issue("warning", "stance_target_unknown", loc, "Target not identified; label alone is insufficient"))
                if field == "relation" and (not isinstance(item.get("target_turn_id"), str) or (record["session_id"], record["source_revision"], item.get("target_turn_id")) not in lookup):
                    issues.append(Issue("error", "relation_reference", loc, "Relation target must exist within the same session/revision"))
    result = report(issues, len(records))
    result["cardinality_status"] = "object_or_list_tolerated_for_review_not_finalized"
    return result
