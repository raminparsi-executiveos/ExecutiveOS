# Final Product Review

Representative workflows were exercised against the API and shipping frontend.

## Completed checklist

- [x] Prevent meeting prep from filling unmatched sections with unrelated company memory.
- [x] Add regression coverage for cross-company and unknown meeting contexts.
- [x] Replace prefilled demo content with example placeholders so sample data is never mistaken for user input.
- [x] Show a useful empty state when capture cannot produce reliable structured updates.
- [x] Prevent saving a capture when no suggested updates are selected.
- [x] Display the selected update count before confirmation.
- [x] Clear stale classification results when the capture text changes.
- [x] Reset capture state after a successful save.
- [x] Support Enter to submit meeting prep and search.
- [x] Improve small-screen navigation and panel layout.
- [x] Add a dependency lockfile so the documented frontend build is reproducible.
- [x] Preserve visible AI-versus-local-preview labeling and explicit user approval.
- [x] Scope named-company search results so broad language cannot pull in other companies.
- [x] Answer `why`, `role`, `company`, and `owner` questions with the matching structured field.
- [x] Support broad decision-review questions even when they do not name a decision.
- [x] Extract high-confidence project ownership, metrics, roles, and decisions in local preview mode.
- [x] Never suggest or report unsupported `note` objects as saved memory.
- [x] Enrich company meeting prep from stored company projects, KPIs, people, and issues.
- [x] Deduplicate shorthand company-index labels against richer normalized records.
- [x] Clearly label a meeting agenda when no matching memory was found.
- [x] Show decision reasoning, owners, roles, values, trends, and risks during capture approval.
- [x] Stress-test 28 additional records across four companies and 33 varied search questions.
- [x] Prevent generic meeting words from leaking other companies' actions into meeting prep.
- [x] Return responsibilities, project next steps, decision review dates, and metric trends directly.
- [x] Aggregate multi-record risks, decisions, action items, metrics, and open questions into useful answers.
- [x] Support honest `today` and `overdue` queries without returning unrelated memory.
- [x] Match conservative singular/plural variants such as `distributors` and `Distributor count`.

## Sample acceptance scenarios

| Input | Expected output |
| --- | --- |
| `Why did we promote Julio?` | Julio's promotion decision is first; unrelated companies are absent. |
| `What is Julio's company?` | Julio at PEC is first. |
| `RYSE leadership meeting` | RYSE context appears; PEC decisions and PM-quality issues do not. |
| `Completely New Topic` | Meeting-prep context sections remain empty instead of inventing relevance. |
| `Morgan owns the Zephyr expansion...` | Capture suggestions require review; only selected updates are saved. |
| Unstructured text with no reliable entities | A clear empty state appears and saving is unavailable. |
| `What is happening at RYSE?` | Only RYSE company and issue context appears. |
| `Who owns PM quality?` | The direct answer is `Julio`. |
| `Revenue is $2.4M, up 12% this quarter.` | Local preview proposes a Revenue metric with the full decimal value and trend. |
| `We decided to pause the Atlas launch because compliance is not ready.` | Local preview preserves both the decision and its reasoning. |

## Verification commands

- `python -m pytest -q`
- `cd frontend && npm run build`
