# GI-Gemma initial public design

Status: candidate design, synthetic-only verification. Updated 2026-10-06.

## Purpose and first-snapshot scope

Prepare an evidence-grounded conversation-analysis specialist while preserving source provenance and the application's existing authority boundaries. This snapshot publishes structural validators and deterministic synthetic contract checks. It is not the full private research specification and does not install a new orchestrator or replace a production model.

## 1. Preserve source identity

The provisional canonical key is `(session_id, source_revision, turn_id)`. Rows keep their supplied text, anonymous speaker ID, timestamps, confidence values, and unknown fields. Validation does not silently sort, drop, normalize, anonymize, infer missing values, or create labels.

The candidate profile requires `session_id`, `source_revision`, `turn_id`, `speaker_id`, `text`, `start_ms`, `end_ms`, and `asr_confidence`. Missing values remain explicit. Null speakers remain unknown. Confidence values need their own source and scale before interpretation. These profile choices still require schema review.

Evidence spans use an explicit proposed policy: Unicode code-point offsets, half-open intervals, and exact quoted text. UTF-16 positions, byte offsets, and normalized text are not interchangeable. References must resolve within the correct session and source revision.

Windows retain original turn IDs and order. All revisions and windows of the same session stay together during splitting. A single session cannot establish independent train, development, and test evaluation. Structural validity does not establish semantic correctness or annotation approval.

## 2. Keep specialist proposals separate from execution

The candidate envelope has four top-level keys:

- `contract_version`
- `decision`, with `kind` and a short `reason`
- `supporting_result_ids`
- `gurumoji_result`, with `summary`, `claims`, `analysis_requests`, and `label_patches`

The specialist returns one of `request_analysis`, `finish`, or `needs_human`. A request contains exactly one proposed analysis. The other decisions contain none. `finish` ends the specialist response; it does not declare the entire run complete or a research conclusion approved. Claims distinguish observation, interpretation, and hypothesis and cite supplied evidence.

The specialist cannot execute a tool or directly update a label. Core owns adoption. Handler owns dispatch, task and result identities, budget, deadline, cancellation, deduplication, persistence, and acceptance of observations. This snapshot tests those boundaries with fixed mock inputs only.

The candidate allowlist is `participation`, `conversation_dynamics`, and `label_frequency`. Participation and dynamics proposals address the full fixed snapshot. Label frequency can address the full snapshot or a valid evidence subset; its pilot label field is `codes`. No shell, arbitrary code, URLs, credential operations, uploads, or publishing are available as model tools.

## 3. Fail closed at the boundary

- Reject malformed types, unknown keys, unsupported methods, conflicting decisions, unseen evidence, and stale or forged result references
- Treat model-visible evidence coverage separately from the Handler's available snapshot
- Require an explicit trusted Core adoption before mock dispatch
- Recheck budget, deadline, cancellation, snapshot availability, and duplicate intent before dispatch
- Keep unknown outcomes unknown and do not automatically retry them
- Permit only a bounded, explicitly recorded retry of an action known not to have been dispatched
- Quarantine late, stale, unvalidated, or replayed observations
- Keep missing, failed, and unexecuted outcomes distinct from successful zero-count results

These checks constrain the application boundary. They do not prove that a model makes safe or correct proposals.

## 4. Compare the simplest baseline first

The research comparison order remains:

1. BASE0: unchanged base-model / zero-shot baseline
2. BASE1: prompt and runtime improvements without changing model weights
3. A small QLoRA smoke check to verify the training path, followed by BASE2: QLoRA comparison
4. Separate, gradual custom-structure or additional representation ablations only after the simpler baselines

The smoke check is an engineering prerequisite, not a substitute for a baseline result or a reordered research comparison. The exact model revision, loading path, dataset version, codebook, evaluation split, seed, configuration, and resource accounting must be fixed and recorded for each real run. This commit does not claim that any model run occurred.

Evaluate classification and relation tasks against approved human labels. Separately measure action selection, argument validity, evidence-grounded task completion, stopping and human-confirmation behavior, forbidden proposals and actual executions, and resource use. Include failed, stopped, and budget-limited episodes in reporting. Synthetic expected outputs are test fixtures, not human gold.

## 5. Remaining decisions and limitations

- Final schema requirements, label definitions and cardinality, and offset policy need review
- Real-data use, participant permissions where applicable, and publication approval are separate from code publication
- Human annotation, independent checking, and adjudication are not replaced by synthetic fixtures
- Native production integration and persistent-state restoration are absent
- Successful conversation-dynamics payloads are deliberately rejected by the mock because they are not implemented
- The synthetic participation payload is not a claim of native application compatibility
- Model loading, inference, training, and model-behavior evaluation remain outside the verification reported here

Later source additions should preserve the same publication boundary and record tests, work-log updates, repository status, and commit identity in that order.
