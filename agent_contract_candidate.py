"""Synthetic-only contract harness for an existing Gurumoji specialist boundary.

This is not a production Handler or a new orchestrator. It has no external I/O,
tool client, model, shell, network, credential or label-write capability.
Specialist proposals are inert until a separate trusted mock Core adopts them.
"""
import copy
import hashlib
import json
import math

CONTRACT = "gigemma-specialist-agent-pilot-1"
INTENT_KEYS = frozenset("role kind result_id initial_sections question why_now success_criteria method_id label_field evidence_ids importance importance_reason dependencies label_dependent replicate_id".split())
METHODS = frozenset(("participation", "conversation_dynamics", "label_frequency"))
OBS_KEYS = frozenset("task_id result_id status method_id data_version annotation_version codebook_version evidence_ids payload".split())
OBS_STATUS = frozenset(("succeeded", "failed", "unknown", "cancelled", "rejected", "duplicate"))
MAX_JSON_BYTES = 65536


class ContractError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise ContractError(code)


def object_keys(value, required):
    require(isinstance(value, dict), "reject_type")
    require(not (set(value) - set(required)), "reject_unknown_key")
    require(set(value) == set(required), "reject_missing_key")


def text(value, *, allow_empty=False, limit=4000):
    require(isinstance(value, str), "reject_type")
    require(len(value) <= limit, "reject_size")
    require(allow_empty or bool(value.strip()), "reject_empty_string")


def ids(value, *, limit=80):
    require(isinstance(value, list), "reject_type")
    require(len(value) <= limit, "reject_size")
    for entry in value:
        text(entry, limit=256)
    require(len(set(value)) == len(value), "reject_duplicate_id")


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def same_versions(observation, state):
    return (isinstance(observation.get("data_version"), str)
            and type(observation.get("annotation_version")) is int
            and type(observation.get("codebook_version")) is int
            and all(observation.get(k) == state.get(k) for k in ("data_version", "annotation_version", "codebook_version")))


def state_shape(state):
    require(isinstance(state, dict), "reject_state")
    require(state.get("contract_version") == CONTRACT, "reject_contract_version")
    text(state.get("episode_id"), limit=256)
    text(state.get("data_version"), limit=256)
    require(type(state.get("step_index")) is int and state["step_index"] >= 0, "reject_state")
    for field in ("annotation_version", "codebook_version"):
        require(type(state.get(field)) is int and state[field] >= 0, "reject_state")
    for field in ("evidence_ids", "provided_evidence_ids", "known_task_ids"):
        ids(state.get(field), limit=512)
    require(set(state["provided_evidence_ids"]) <= set(state["evidence_ids"]), "reject_state")
    require(type(state.get("cancel_requested")) is bool, "reject_state")
    require(type(state.get("runner_snapshot_complete")) is bool, "reject_state")
    require(isinstance(state.get("raw_evidence"), list), "reject_state")
    raw_ids = []
    for row in state["raw_evidence"]:
        require(isinstance(row, dict), "reject_state")
        text(row.get("evidence_id"), limit=256)
        text(row.get("text"), allow_empty=True, limit=32000)
        raw_ids.append(row["evidence_id"])
    require(len(raw_ids) == len(set(raw_ids)), "reject_state")
    require(set(raw_ids) == set(state["provided_evidence_ids"]), "reject_state")
    require(isinstance(state.get("observations"), list), "reject_state")


def validate_candidate(candidate, state, *, trusted_results=None):
    """Validate an envelope; never infer or dispatch an action here."""
    state_shape(state)
    try:
        size = len(json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise ContractError("reject_type")
    require(size <= MAX_JSON_BYTES, "reject_size")
    object_keys(candidate, {"contract_version", "decision", "supporting_result_ids", "gurumoji_result"})
    require(candidate["contract_version"] == CONTRACT, "reject_contract_version")
    decision = candidate["decision"]
    object_keys(decision, {"kind", "reason"})
    require(isinstance(decision["kind"], str) and decision["kind"] in {"request_analysis", "finish", "needs_human"}, "reject_decision")
    text(decision["reason"], limit=2000)
    ids(candidate["supporting_result_ids"], limit=64)
    successful = {}
    # Raw restored state is not evidence of prior validation. Only the Handler's
    # separately held, already-validated results may support a candidate.
    for observation in (trusted_results or []):
        if not isinstance(observation, dict):
            continue
        if (set(observation) == OBS_KEYS and observation.get("status") == "succeeded"
                and same_versions(observation, state)
                and observation.get("task_id") in state["known_task_ids"]
                and isinstance(observation.get("result_id"), str)):
            successful[observation["result_id"]] = observation
    require(set(candidate["supporting_result_ids"]) <= set(successful), "reject_result_provenance")
    result = candidate["gurumoji_result"]
    object_keys(result, {"summary", "claims", "analysis_requests", "label_patches"})
    text(result["summary"])
    require(isinstance(result["claims"], list) and len(result["claims"]) <= 24, "reject_type")
    require(isinstance(result["analysis_requests"], list) and len(result["analysis_requests"]) <= 1, "reject_type")
    require(isinstance(result["label_patches"], list) and result["label_patches"] == [], "reject_label_write")
    requests = result["analysis_requests"]
    require(len(requests) == (1 if decision["kind"] == "request_analysis" else 0), "reject_decision_request_mismatch")
    claim_ids = []
    for claim in result["claims"]:
        object_keys(claim, {"claim_id", "text", "kind", "evidence_ids"})
        text(claim["claim_id"], limit=256); text(claim["text"])
        require(isinstance(claim["kind"], str) and claim["kind"] in {"observation", "interpretation", "hypothesis"}, "reject_claim_kind")
        ids(claim["evidence_ids"])
        require(set(claim["evidence_ids"]) <= set(state["evidence_ids"]), "reject_evidence")
        require(set(claim["evidence_ids"]) <= set(state["provided_evidence_ids"]), "reject_unseen_evidence")
        require(bool(claim["evidence_ids"]), "reject_claim_grounding")
        claim_ids.append(claim["claim_id"])
    require(len(claim_ids) == len(set(claim_ids)), "reject_duplicate_id")
    for request in requests:
        object_keys(request, INTENT_KEYS)
        for field in ("role", "kind", "question", "why_now", "success_criteria", "method_id", "importance", "importance_reason"):
            text(request[field], limit=2000)
        for field in ("result_id", "label_field", "replicate_id"):
            text(request[field], allow_empty=True, limit=256)
        require(type(request["label_dependent"]) is bool, "reject_type")
        for field in ("initial_sections", "dependencies"):
            require(isinstance(request[field], list), "reject_type")
            require(request[field] == [], "reject_pilot_subset")
        require(request["result_id"] == request["replicate_id"] == "", "reject_pilot_subset")
        require(request["role"] == "statistics" and request["kind"] == "analysis", "reject_role")
        require(request["method_id"] in METHODS, "reject_method_allowlist")
        require(request["importance"] in {"low", "medium", "high"}, "reject_importance")
        ids(request["evidence_ids"])
        require(set(request["evidence_ids"]) <= set(state["evidence_ids"]), "reject_evidence")
        if request["method_id"] in {"participation", "conversation_dynamics"}:
            require(request["evidence_ids"] == [] and request["label_field"] == "" and request["label_dependent"] is False, "reject_method_scope")
        else:
            require(request["label_field"] == "codes" and request["label_dependent"] is True, "reject_method_scope")
    return {"decision": decision["kind"], "done": decision["kind"] == "finish",
            "needs_human": decision["kind"] == "needs_human", "run_completed": False,
            "gurumoji_payload": copy.deepcopy(result)}


def intent_fingerprint(request, state):
    """Handler-owned exact normalized-intent identity, not semantic equivalence."""
    identity = {k:state[k] for k in ("episode_id", "data_version", "annotation_version", "codebook_version")}
    identity.update({k:request[k] for k in ("role", "kind", "method_id", "label_field", "label_dependent")})
    identity["evidence_ids"] = sorted(request["evidence_ids"])
    identity["purpose"] = " ".join(request["question"].split())
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class MockHandlerBoundary:
    """Finite in-memory test double. Budget, IDs and retry limits are trusted inputs.

    Does not replace the existing Handler. No production external tool can be
    attached to this class. Only a caller-supplied, fixed synthetic observation is
    accepted, and it must match the IDs/version/scope the stub assigned.
    """
    def __init__(self, state, *, max_predispatch_retries=1):
        require(type(max_predispatch_retries) is int and 0 <= max_predispatch_retries <= 1, "reject_retry_policy")
        self.state = copy.deepcopy(state)
        self.ledger = {}
        self.proposals = []
        self.quarantined = copy.deepcopy(self.state.get("observations", []))
        self.state["observations"] = []
        self.validated_results = []
        self.dispatch_count = 0
        self._serial = 0
        self.accepted_result_ids = set()
        self.max_predispatch_retries = max_predispatch_retries

    def output(self, stage, outcome, before, **extra):
        return {"stage":stage, "outcome":outcome, "dispatch_count":self.dispatch_count-before,
                "external_actions":0, "model_inference_performed":False, **extra}

    def record_not_dispatched_failure(self, request, *, attempts=1):
        require(type(attempts) is int and attempts >= 1, "reject_retry_policy")
        self.ledger[intent_fingerprint(request,self.state)] = {"status":"not_dispatched", "attempts":attempts}

    def seed_trusted_unknown_dispatch(self, request, observation):
        """Test-only ledger setup, not a production persistence/restore adapter."""
        require(isinstance(observation,dict) and observation.get("status") == "unknown", "reject_result_provenance")
        require(same_versions(observation,self.state), "reject_result_provenance")
        require(observation.get("method_id") == request["method_id"], "reject_result_provenance")
        scope = request["evidence_ids"] or self.state["evidence_ids"]
        ids(observation.get("evidence_ids"),limit=512)
        require(set(observation["evidence_ids"]) == set(scope), "reject_evidence")
        for field in ("task_id","result_id"):text(observation.get(field),limit=256)
        entry={k:copy.deepcopy(observation[k]) for k in ("task_id","result_id","method_id","evidence_ids","data_version","annotation_version","codebook_version")}
        entry["scope"]="selected" if request["evidence_ids"] else ("all_included" if request["method_id"] == "label_frequency" else "full")
        entry.update(status="unknown",attempts=1)
        fingerprint=intent_fingerprint(request,self.state)
        require(fingerprint not in self.ledger,"reject_duplicate_id")
        self.ledger[fingerprint]=entry
        if entry["task_id"] not in self.state["known_task_ids"]:self.state["known_task_ids"].append(entry["task_id"])

    def submit(self, candidate, *, mock_core_approved, mock_observation):
        before = self.dispatch_count
        try:
            validated = validate_candidate(candidate, self.state, trusted_results=self.validated_results)
        except ContractError as error:
            return self.output("candidate_validation", error.code, before)
        if self.state["cancel_requested"]:
            self.quarantined.append({"candidate":copy.deepcopy(candidate)})
            return self.output("handler", "cancelled", before)
        now, deadline = self.state.get("now_epoch"), self.state.get("deadline_epoch")
        if not finite_number(now) or not finite_number(deadline):
            return self.output("handler", "deadline_unknown", before)
        if now >= deadline:
            self.quarantined.append({"candidate":copy.deepcopy(candidate)})
            return self.output("handler", "deadline_stop", before)
        self.proposals.append(copy.deepcopy(candidate))
        if validated["decision"] != "request_analysis":
            return self.output("candidate_validation", "valid_"+validated["decision"], before, done=validated["done"], needs_human=validated["needs_human"], run_completed=False)
        if mock_core_approved is not True:
            return self.output("core_gate", "proposal_only", before)
        budget = self.state.get("budget")
        if not isinstance(budget, dict) or any(type(budget.get(k)) is not int or budget[k] < 0 for k in ("remaining_calls","remaining_tasks")):
            return self.output("handler", "budget_unknown", before)
        if min(budget["remaining_calls"], budget["remaining_tasks"]) == 0:
            return self.output("handler", "budget_stop", before)
        request = validated["gurumoji_payload"]["analysis_requests"][0]
        if not self.state["runner_snapshot_complete"]:
            return self.output("handler", "snapshot_unavailable", before)
        if not (request["evidence_ids"] or self.state["evidence_ids"]):
            return self.output("handler", "empty_scope", before)
        fingerprint = intent_fingerprint(request,self.state)
        prior = self.ledger.get(fingerprint)
        attempts = 0
        if prior:
            if prior["status"] == "unknown":
                return self.output("handler", "unknown_no_retry", before)
            if prior["status"] == "not_dispatched":
                attempts = prior["attempts"]
                if attempts > self.max_predispatch_retries:
                    return self.output("handler", "retry_limit", before)
            else:
                return self.output("handler", "duplicate", before)
        self.dispatch_count += 1
        # remaining_calls is a prechecked model-call allowance owned by Core;
        # this stub invokes no model. Only its mock task budget is consumed.
        budget["remaining_tasks"] -= 1
        self._serial += 1
        while f"mock-task-{self._serial:02d}" in self.state["known_task_ids"]:
            self._serial += 1
        task_id = f"mock-task-{self._serial:02d}"
        result_id = f"mock-result-{self._serial:02d}"
        scope = request["evidence_ids"] or self.state["evidence_ids"]
        entry={"status":"pending", "attempts":attempts+1,"task_id":task_id,"result_id":result_id,"method_id":request["method_id"],"evidence_ids":list(scope)}
        entry["scope"]="selected" if request["evidence_ids"] else ("all_included" if request["method_id"] == "label_frequency" else "full")
        entry.update({k:self.state[k] for k in ("data_version","annotation_version","codebook_version")})
        self.ledger[fingerprint] = entry
        self.state["known_task_ids"].append(task_id)
        accepted = self.accept_observation(mock_observation, expected=entry)
        entry["status"] = "unknown" if accepted["outcome"] == "unknown" else accepted["outcome"]
        return self.output(accepted["stage"],accepted["outcome"],before, observation=accepted.get("observation"))

    def accept_observation(self, observation, *, expected=None):
        before = self.dispatch_count
        if not finite_number(self.state.get("now_epoch")) or not finite_number(self.state.get("deadline_epoch")):
            self.quarantined.append(copy.deepcopy(observation))
            return self.output("observation_validation", "deadline_unknown", before)
        if self.state.get("cancel_requested") is True or (finite_number(self.state.get("now_epoch")) and finite_number(self.state.get("deadline_epoch")) and self.state["now_epoch"] >= self.state["deadline_epoch"]):
            self.quarantined.append(copy.deepcopy(observation))
            return self.output("observation_validation", "quarantined", before)
        try:
            object_keys(observation, OBS_KEYS)
            require(expected is not None, "reject_result_provenance")
            for field in ("task_id", "result_id", "method_id"):
                require(observation.get(field) == expected[field], "reject_result_provenance")
            require(isinstance(observation["status"], str) and observation["status"] in OBS_STATUS, "reject_type")
            require(same_versions(observation,self.state) and same_versions(observation,expected), "reject_result_provenance")
            ids(observation["evidence_ids"], limit=512)
            require(set(observation["evidence_ids"]) == set(expected["evidence_ids"]), "reject_evidence")
            require(isinstance(observation["payload"], dict), "reject_type")
            if observation["status"] == "succeeded" and observation["method_id"] == "label_frequency":
                payload = observation["payload"]
                denominator = payload.get("denominator")
                missing = payload.get("missing_count")
                require(type(denominator) is int and denominator == len(expected["evidence_ids"]), "reject_result_payload")
                require(type(missing) is int and 0 <= missing <= denominator, "reject_result_payload")
                require(isinstance(payload.get("rows"), list), "reject_result_payload")
                labels=[]
                nonmissing_ids=set()
                for row in payload["rows"]:
                    require(isinstance(row,dict), "reject_result_payload")
                    text(row.get("label"), limit=256)
                    labels.append(row["label"])
                    require(type(row.get("count")) is int and 0 <= row["count"] <= denominator, "reject_result_payload")
                    require(type(row.get("denominator")) is int and row["denominator"] == denominator, "reject_result_payload")
                    ids(row.get("evidence_ids"), limit=512)
                    require(set(row["evidence_ids"]) <= set(expected["evidence_ids"]), "reject_evidence")
                    require(len(row["evidence_ids"]) == row["count"], "reject_result_payload")
                    nonmissing_ids.update(row["evidence_ids"])
                    if denominator:
                        require(finite_number(row.get("proportion")) and abs(row["proportion"]-row["count"]/denominator) < 1e-9, "reject_result_payload")
                require(len(labels)==len(set(labels)) and len(nonmissing_ids)==denominator-missing,"reject_result_payload")
                manifest = payload.get("manifest")
                require(isinstance(manifest,dict) and manifest.get("source_kind") == "synthetic" and manifest.get("kind") == "deterministic_code", "reject_result_provenance")
                require(manifest.get("method_version") == "label-frequency-1", "reject_result_provenance")
                require(manifest.get("analysis_unit") == "utterance" and expected.get("scope") in {"selected","all_included"} and manifest.get("scope") == expected.get("scope"),"reject_result_provenance")
                require(manifest.get("dataset_version") == self.state["data_version"], "reject_result_provenance")
                for field in ("annotation_version","codebook_version"):
                    require(type(manifest.get(field)) is int and manifest[field] == self.state[field], "reject_result_provenance")
                ids(manifest.get("evidence_ids"), limit=512)
                require(set(manifest["evidence_ids"]) == set(expected["evidence_ids"]), "reject_evidence")
            elif observation["status"] == "succeeded" and observation["method_id"] == "participation":
                payload=observation["payload"]
                object_keys(payload,{"payload_version","source_kind","total_turns","speaker_counts","manifest"})
                require(payload["payload_version"] == "synthetic-participation-1" and payload["source_kind"] == "synthetic", "reject_result_payload")
                require(type(payload["total_turns"]) is int and payload["total_turns"] == len(expected["evidence_ids"]),"reject_result_payload")
                counts=payload["speaker_counts"]
                require(isinstance(counts,dict),"reject_result_payload")
                speaker_ids=self.state.get("runner_speaker_ids")
                ids(speaker_ids,limit=512)
                require(set(counts) == set(speaker_ids),"reject_result_payload")
                require(all(type(v) is int and v>=0 for v in counts.values()) and sum(counts.values()) == payload["total_turns"],"reject_result_payload")
                manifest=payload["manifest"]
                object_keys(manifest,{"kind","source_kind","method_version","analysis_unit","scope","evidence_ids","dataset_version","annotation_version","codebook_version"})
                require(manifest["kind"] == "deterministic_code" and manifest["source_kind"] == "synthetic" and manifest["method_version"] == "synthetic-participation-1", "reject_result_provenance")
                require(manifest["analysis_unit"] == "utterance" and manifest["scope"] == "full", "reject_result_provenance")
                require(manifest["dataset_version"] == expected["data_version"],"reject_result_provenance")
                for field in ("annotation_version","codebook_version"):
                    require(type(manifest[field]) is int and manifest[field] == expected[field],"reject_result_provenance")
                ids(manifest["evidence_ids"],limit=512)
                require(set(manifest["evidence_ids"]) == set(expected["evidence_ids"]),"reject_evidence")
            elif observation["status"] == "succeeded":
                # Native dynamics datasets are not implemented in this mock.
                require(False,"reject_unsupported_payload")
        except ContractError as error:
            self.quarantined.append(copy.deepcopy(observation))
            return self.output("observation_validation",error.code,before)
        clean = copy.deepcopy(observation)
        if clean["result_id"] in self.accepted_result_ids:
            return self.output("observation_validation", "duplicate", before)
        if clean["status"] == "succeeded":
            self.accepted_result_ids.add(clean["result_id"])
            self.state["observations"].append(clean)
            self.validated_results.append(copy.deepcopy(clean))
        else:
            self.quarantined.append(clean)
        return self.output("handler",clean["status"],before,observation=clean)
