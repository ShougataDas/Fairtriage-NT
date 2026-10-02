# Extraction evaluation: keyword, split=test

Rows scored: 1810 (errors 0). Label sources: {'derived': 1800, 'probe_designed': 10}.

> **Most labels here are derived by rule, not human.** These numbers measure agreement with the migration rule. Do not quote them as accuracy. Re-run on the blind-annotated set and report kappa beside the result.

## Per-field macro-F1

| Field | Macro-F1 |
|---|---|
| actionability | 0.835 |
| endangers_person | 0.963 |
| essential_service_lost | 0.522 |

## Safety

- **Critical-hazard false-negative rate:** 10.0% (52 of 518 dangerous reports missed)
- **False dismissal rate:** 0.2% (1 dangerous reports routed out of the queue)
- Normalisation changed the reading on 1.3% of messages; each would be escalated to a human.

Danger precision 0.998, recall 0.900.

## By challenge type

| Challenge | n | Actionability acc. | Danger acc. |
|---|---|---|---|
| buried_hazard | 2 | 100.0% | 100.0% |
| false_withdrawal | 2 | 100.0% | 100.0% |
| insufficient_detail | 95 | 57.9% | 100.0% |
| multi_issue | 348 | 99.1% | 97.1% |
| negation | 129 | 100.0% | 100.0% |
| normal_state | 141 | 77.3% | 100.0% |
| possible_hazard_unclear | 85 | 100.0% | 100.0% |
| register_pair | 4 | 100.0% | 100.0% |
| standard | 797 | 89.1% | 96.0% |
| typo | 205 | 93.7% | 95.1% |
| understated_severity | 2 | 100.0% | 50.0% |

## Paraphrase invariance

1 of 1 paraphrase groups read identically across registers.
With only 1 groups this is a smoke test, not a measurement. Aim for 40 or more.
