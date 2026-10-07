# GI-Gemma: public design and synthetic contract checks

GI-Gemma is a research prototype for evidence-grounded conversation analysis. This first public snapshot contains a deliberately limited, reviewed subset of the design and candidate validation code.

## Status

- Candidate canonical-data and evidence-reference validation
- Candidate Specialist → Core → Handler contract with a deterministic mock executor
- Invented synthetic fixtures only
- 36 canonical checks and 54 agent-boundary checks passed in separate Colab CPU runs on 2026-10-06
- Model loading, generation, training, model behavior, production integration, and human-gold accuracy have **not** been verified by these checks

The 90 checks exercise data structure and mock execution boundaries. They do not establish research-label correctness, participant permission, prompt-injection resistance of a model, or training effectiveness.

## Files

- `canonical_candidate.py` and `test_canonical_candidate.py`: provisional row, evidence-span, revision, window, and split validation
- `agent_contract_candidate.py` and `test_agent_contract_candidate.py`: strict output validation and a finite synthetic Handler test double
- `agent-contract-fixture-candidates-v2.json`: current synthetic acceptance cases
- `agent-baseline-prompt-v1.txt`: candidate specialist prompt
- `agent-trajectory-example-v1.json`: synthetic trajectory illustration
- [Design](DESIGN.md): scope, boundaries, and research order
- [Validation record](docs/VALIDATION.md): exact tested source hashes, outcomes, and limits
- [Source hash manifest](verification/source-sha256.json): frozen published source identities

## Reproduce the synthetic checks

From this directory, using Python 3.13 (the recorded runtime was Python 3.13.16):

```sh
python -m unittest -v test_canonical_candidate test_agent_contract_candidate
```

These files use the Python standard library. Keep the fixture JSON next to the agent test module, as in this snapshot. Tests do not load a model, contact a service, or consume real transcripts.

## Publication boundary

This repository is public. Do not add real transcripts, participant details, private source links or storage identifiers, local work logs, credentials, checkpoints, model weights, executed notebook outputs, or derived artifacts that may reproduce private data. A public code repository does not grant permission to publish source data or trained artifacts.

The original private research materials, full architecture documents, annotation decisions, data adapters, and model-loading notebooks are outside this initial snapshot. The public source is a candidate for review, not a completed production system.
