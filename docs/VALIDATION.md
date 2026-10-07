# Validation record for the initial public snapshot

The executable sources, tests, fixture, prompt, and trajectory in this snapshot are byte-for-byte copies of the frozen preparation artifacts listed in `verification/source-sha256.json`.

## Recorded execution

Both checks ran on Colab CPU with Python 3.13.16. No GPU, model load, generation, training, external tool call, real transcript, or human-gold creation was part of these runs.

| Suite | Completed at UTC | Tests | Failures | Errors |
| --- | --- | ---: | ---: | ---: |
| Canonical structural candidates | 2026-10-06 18:56:27 | 36 | 0 | 0 |
| Agent contract, revision 2 | 2026-10-06 19:23:13 | 54 | 0 | 0 |

The agent run used fixture revision `synthetic-boundary-v2`. An earlier 38-test agent run is superseded by the 54-test run. Its historical files are not included here.

## What was checked

Canonical checks cover lossless JSONL, duplicate and invalid identifiers, missing fields, unchanged row order, confidence scale, finite timestamp values, source revisions, session-grouped splits, explicit evidence references, and Unicode spans. A deterministic 250-sample round-trip test is one of the 36 tests, not 250 additional test cases.

Agent checks cover 18 acceptance scenarios and 36 additional boundary cases: strict types and unknown keys, valid proposal adoption, disallowed methods, evidence and result provenance, coverage, budgets, deadlines, cancellation, deduplication, unknown outcomes, late observations, retry bounds, payload consistency, and forged state. All dispatches are in-memory mock actions.

## Limits

Passing these checks does not approve the candidate schema or codebook. It does not measure model accuracy, semantic judgment, prompt-injection resistance, training effectiveness, production integration, or consent. The prompt and trajectory are frozen companion artifacts; the test counts do not mean they were evaluated through a model.

Private execution reports and executed notebooks are excluded. This file is a minimal public summary. Source hashes permit identity checks; they do not replace reproducing the tests in the intended runtime.
