"""All fixtures are invented. Passing tests do not approve the proposed schema."""
import copy
import json
import random
import unittest
import canonical_candidate as c


def row(turn="T01", speaker="S01", text="読書会を土曜に開きませんか。", session="SYNTH-A", revision="synthetic-r1"):
    return {"session_id": session, "source_revision": revision, "turn_id": turn,
            "speaker_id": speaker, "text": text, "start_ms": None, "end_ms": None, "asr_confidence": None}


def fixtures():
    return [row(), row("T02", "S02", "土曜なら参加できます。"), row("T03", None, "うーん、確認します。")]


def codes(report):
    return {i["code"] for i in report["issues"]}


class CanonicalTests(unittest.TestCase):
    def test_valid_rows_and_unknown_speaker_remain_candidate(self):
        r = c.validate_canonical(fixtures())
        self.assertEqual(r["error_count"], 0)
        self.assertEqual(r["status"], "review_required")
        self.assertIn("speaker_unknown", codes(r))
        self.assertFalse(r["gold_promoted"])

    def test_no_mutation_sorting_or_null_imputation(self):
        rows = fixtures(); before = copy.deepcopy(rows)
        c.validate_canonical(rows, expected_order=[c.key(x) for x in rows])
        self.assertEqual(rows, before)
        self.assertIsNone(rows[-1]["speaker_id"])
        self.assertTrue(all(x["start_ms"] is None and x["asr_confidence"] is None for x in rows))

    def test_duplicate_turn_detected(self):
        self.assertIn("duplicate_turn", codes(c.validate_canonical([row(), row()])))

    def test_same_turn_id_in_distinct_sessions_allowed(self):
        self.assertEqual(c.validate_canonical([row(), row(session="SYNTH-B")])["error_count"], 0)

    def test_invalid_ids_fail_without_crash(self):
        for bad in [None, "", " ", [], {}, 1, True]:
            for field in ("session_id", "source_revision", "turn_id"):
                with self.subTest(field=field, value_type=type(bad).__name__):
                    r = row(); r[field] = bad
                    self.assertIn("invalid_id", codes(c.validate_canonical([r])))

    def test_missing_fields_are_not_filled(self):
        r = row(); del r["end_ms"]
        self.assertIn("missing_field", codes(c.validate_canonical([r])))
        self.assertNotIn("end_ms", r)

    def test_invalid_container_and_row_type(self):
        self.assertIn("rows_type", codes(c.validate_canonical({})))
        self.assertIn("row_type", codes(c.validate_canonical([None, 2])))

    def test_empty_text_retained_for_review(self):
        r = row(text="")
        self.assertIn("text_empty", codes(c.validate_canonical([r])))
        self.assertEqual(r["text"], "")

    def test_partial_time_is_not_synthesized(self):
        r = row(); r["start_ms"] = 13.259
        self.assertIn("timestamp_partial", codes(c.validate_canonical([r])))
        self.assertIsNone(r["end_ms"])

    def test_bad_timestamp_types_and_nonfinite_rejected(self):
        for bad in [-1, True, "5", float("nan"), float("inf"), 10**1000, {}]:
            with self.subTest(value_type=type(bad).__name__):
                r = row(); r["start_ms"] = bad
                self.assertIn("timestamp_type", codes(c.validate_canonical([r])))

    def test_end_before_start_rejected(self):
        r = row(); r.update(start_ms=20, end_ms=10)
        self.assertIn("timestamp_order", codes(c.validate_canonical([r])))

    def test_overlapping_turns_not_rejected_as_reordering(self):
        rows = [row(), row("T02", "S02")]
        rows[0].update(start_ms=0, end_ms=1000)
        rows[1].update(start_ms=500, end_ms=1200)
        self.assertEqual(c.validate_canonical(rows, expected_order=[c.key(x) for x in rows])["error_count"], 0)

    def test_reordered_rows_detected_only_with_explicit_reference(self):
        rows = fixtures(); order = [c.key(x) for x in rows]
        self.assertIn("source_order_mismatch", codes(c.validate_canonical(list(reversed(rows)), expected_order=order)))
        self.assertFalse(c.validate_canonical(rows)["source_order_checked"])

    def test_asr_scale_not_assumed(self):
        r = row(); r["asr_confidence"] = 80.0
        unscaled = c.validate_canonical([r])
        self.assertEqual(unscaled["error_count"], 0)
        self.assertIn("asr_provenance_missing", codes(unscaled))
        self.assertEqual(c.validate_canonical([r], asr_metadata={"source":"synthetic","scale":"percent","range":[0,100]})["error_count"], 0)
        self.assertIn("asr_out_of_range", codes(c.validate_canonical([r], asr_metadata={"source":"synthetic","scale":"fraction","range":[0,1]})))

    def test_revision_mixing_flagged(self):
        self.assertIn("multiple_revisions", codes(c.validate_canonical([row(), row(revision="synthetic-r2")])))

    def test_jsonl_roundtrip_preserves_unknown_fields_unicode_newlines(self):
        rows = [row(text="A😀\nか\u3099　\r\n土曜"), row("T02", None, "同じ 同じ")]
        rows[0]["source_note"] = {"provided": None, "fixture_only": True}
        wire = c.encode_jsonl(rows)
        self.assertEqual(c.decode_jsonl(wire), rows)
        self.assertEqual(len(wire.splitlines()), 2)

    def test_json_duplicate_keys_nonfinite_and_blank_records_fail(self):
        for wire in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{}\n\n', '[]\n']:
            with self.subTest(wire=wire):
                with self.assertRaises(ValueError): c.decode_jsonl(wire)

    def test_writer_rejects_nonfinite(self):
        r = row(); r["asr_confidence"] = float("nan")
        with self.assertRaises(ValueError): c.encode_jsonl([r])

    def test_deterministic_fuzz_roundtrip_250_samples(self):
        rng = random.Random(20261006)
        alphabet = ["あ", "か\u3099", "😀", "\n", "\r", "\t", "　", "\"", "\\", "e\u0301", "\u2028", "\u0085"]
        for i in range(250):
            r = row(turn=f"T{i:04}", text="".join(rng.choice(alphabet) for _ in range(rng.randrange(1,100))))
            self.assertEqual(c.decode_jsonl(c.encode_jsonl([r])), [r])


class WindowSplitTests(unittest.TestCase):
    def test_overlapping_windows_preserve_references(self):
        rows = fixtures()
        windows = [{"window_id":"W1","session_id":"SYNTH-A","source_revision":"synthetic-r1","turn_ids":["T01","T02"]},
                   {"window_id":"W2","session_id":"SYNTH-A","source_revision":"synthetic-r1","turn_ids":["T02","T03"]}]
        self.assertEqual(c.validate_windows(windows, rows)["error_count"], 0)

    def test_cross_session_window_target_fails(self):
        w = {"window_id":"W1","session_id":"SYNTH-A","source_revision":"synthetic-r1","turn_ids":["T99"]}
        self.assertIn("window_cross_reference", codes(c.validate_windows([w], fixtures()+[row("T99",session="SYNTH-B")])))

    def test_window_order_duplicate_and_malformed_group_fail(self):
        w = {"window_id":"W1","session_id":"SYNTH-A","source_revision":"synthetic-r1","turn_ids":["T02","T01","T01"]}
        result = c.validate_windows([w],fixtures())
        self.assertTrue({"window_order","window_turn_duplicate"} <= codes(result))
        w["session_id"] = []
        self.assertIn("window_group_type", codes(c.validate_windows([w],fixtures())))

    def test_one_session_cannot_be_independent_train_dev_test(self):
        assignments = [{"session_id":"SYNTH-A","source_revision":"synthetic-r1","split":"train"}]
        result = c.validate_splits(assignments, fixtures(), require_independent_eval=True)
        self.assertIn("independent_eval_unavailable", codes(result))

    def test_revisions_of_same_session_cannot_cross_splits(self):
        rows=[row(),row(revision="synthetic-r2")]
        a=[{"session_id":"SYNTH-A","source_revision":"synthetic-r1","split":"train"},
           {"session_id":"SYNTH-A","source_revision":"synthetic-r2","split":"test"}]
        self.assertIn("session_leakage", codes(c.validate_splits(a,rows)))

    def test_three_distinct_synthetic_sessions_pass_structural_split_check(self):
        rows=[row(session=s) for s in ("SYNTH-A","SYNTH-B","SYNTH-C")]
        a=[{"session_id":r["session_id"],"source_revision":r["source_revision"],"split":s} for r,s in zip(rows,("train","dev","test"))]
        self.assertEqual(c.validate_splits(a,rows,require_independent_eval=True)["error_count"],0)

    def test_bad_split_types_and_missing_coverage_fail(self):
        self.assertIn("split_coverage", codes(c.validate_splits([], fixtures())))
        self.assertIn("split_field_type", codes(c.validate_splits([{"session_id":[],"split":[]}], fixtures())))


class EvidenceReferenceTests(unittest.TestCase):
    def setUp(self):
        self.rows=[row(text="A😀\nか\u3099 同じ 同じ"),row("T02","S02","土曜に賛成です。")]

    def evidence(self, start, end, quote, **extra):
        return {"turn_id":"T01","text_span":{"start_char":start,"end_char":end,"quote":quote},**extra}

    def check(self, evidence):
        return c.validate_evidence(evidence,self.rows,session_id="SYNTH-A",source_revision="synthetic-r1",offset_policy="unicode_codepoints_half_open_proposal_v0")

    def test_unicode_codepoint_emoji_and_combining_sequence(self):
        self.assertEqual(self.check([self.evidence(1,2,"😀"),self.evidence(3,5,"か\u3099")])["error_count"],0)

    def test_utf16_byte_or_normalized_offset_does_not_pass(self):
        self.assertIn("quote_mismatch",codes(self.check([self.evidence(1,3,"😀") ])))
        self.assertIn("quote_mismatch",codes(self.check([self.evidence(3,5,"が") ])))

    def test_repeated_quote_resolved_by_explicit_span(self):
        text=self.rows[0]["text"]; first=text.index("同じ");second=text.index("同じ",first+1)
        self.assertEqual(self.check([self.evidence(second,second+2,"同じ")])["error_count"],0)

    def test_old_revision_unknown_turn_and_bad_reference_types_fail(self):
        self.assertIn("evidence_reference",codes(self.check([self.evidence(0,1,"A",source_revision="synthetic-r0")])))
        e=self.evidence(0,1,"A");e["turn_id"]=[]
        self.assertIn("evidence_reference_type",codes(self.check([e])))

    def test_bounds_and_boolean_offsets_fail(self):
        for start,end in [(False,1),(-1,1),(1,1),(0,999)]:
            with self.subTest(start=start,end=end):self.assertIn("span_bounds",codes(self.check([self.evidence(start,end,"A")])))

    def test_offset_policy_must_be_explicit(self):
        r=c.validate_evidence([],self.rows,session_id="SYNTH-A",source_revision="synthetic-r1",offset_policy=None)
        self.assertIn("offset_policy",codes(r))

    def ir(self):
        return {"session_id":"SYNTH-A","source_revision":"synthetic-r1","turn_id":"T02","speaker_id":"S02", "dialogue_act":["agreement"],"stance":{"target":"土曜の読書会","label":"support"},"relation":{"target_turn_id":"T01","type":"reply_to"}}

    def test_ir_reference_and_candidate_vocabularies(self):
        r=c.validate_ir_references([self.ir()],self.rows)
        self.assertEqual(r["error_count"],0);self.assertFalse(r["gold_promoted"])
        self.assertEqual(r["cardinality_status"],"object_or_list_tolerated_for_review_not_finalized")

    def test_ir_unknown_labels_missing_target_and_cross_session_fail(self):
        ir=self.ir();ir["dialogue_act"]=["invented"]
        ir["stance"]={"target":None,"label":"unclear"}
        ir["relation"]={"target_turn_id":"UNKNOWN","type":"reply_to"}
        found=codes(c.validate_ir_references([ir],self.rows))
        self.assertTrue({"da_label","stance_target_unknown","relation_reference"} <= found)

    def test_ir_malformed_key_and_relation_reference_fail_without_crash(self):
        ir=self.ir();ir["turn_id"]=[]
        self.assertIn("ir_reference_type",codes(c.validate_ir_references([ir],self.rows)))
        ir=self.ir();ir["relation"]["target_turn_id"]={}
        self.assertIn("relation_reference",codes(c.validate_ir_references([ir],self.rows)))

    def test_neutral_unclear_and_unreviewed_not_coerced(self):
        ir=self.ir(); ir["stance"]["label"]="unclear";ir["review_state"]="unreviewed"
        before=copy.deepcopy(ir);c.validate_ir_references([ir],self.rows)
        self.assertEqual(ir,before);self.assertNotEqual(ir["stance"]["label"],"neutral")


if __name__ == "__main__":
    unittest.main()
