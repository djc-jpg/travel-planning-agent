# Eval Rubric

## Scope
This rubric is used for human spot checks on cases that already passed automated checks.
It focuses on customer-facing quality that is hard to score purely by rules.

## Manual Metric 1: Usability & Value (0-5)
Score whether a customer can execute the itinerary with minimal extra planning.

- `0`: Not usable. Missing key logistics, impossible timeline, no backups.
- `1`: Major gaps. Frequent ambiguity in timing/transport/meal/rest.
- `2`: Partially usable. Some actionable info but multiple execution blockers.
- `3`: Usable with minor edits. Main timeline works, but risk handling is thin.
- `4`: Strong. Clear daily flow, practical buffers, clear alternatives.
- `5`: Excellent. Immediately executable, with proactive risk controls and tradeoff notes.

Review checklist:
- Are transport and queue/security buffers explicit?
- Are lunch/rest windows present and reasonable?
- Are fallback options provided for crowd/weather disruption?
- Is budget breakdown clear and actionable?

## Manual Metric 2: Personalization (0-5)
Score whether plan truly reflects user preferences and constraints.

- `0`: Ignores user profile and constraints.
- `1`: Mentions preferences but does not affect itinerary.
- `2`: Limited adaptation; many generic recommendations.
- `3`: Good adaptation to major constraints.
- `4`: Strong adaptation to both preferences and operational constraints.
- `5`: Excellent adaptation with clear rationale for choices and tradeoffs.

Review checklist:
- Are must-visit and avoid requirements respected?
- Is pace aligned with group type (family/elderly/solo/etc.)?
- Are dietary/mobility constraints reflected in choices and timing?
- Is content style aligned with stated goals (history/food/photo/etc.)?

## Suggested Sampling
- Evaluate at least 5 representative cases per release:
  1. Beijing Spring Festival peak case
  2. Low-budget feasibility warning case
  3. Family/parent-child case
  4. Mobility-limited case
  5. Tight schedule must-visit case
