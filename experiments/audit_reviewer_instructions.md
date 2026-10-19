# Reviewer instructions (given verbatim to each blind Claude subagent)

You are adjudicating drug→disease indication edges against regulator label text. Read the
rubric in `experiments/audit_rubric.md` first and apply it exactly.

Input: `experiments/out/v2/batch<ROUND>_<REVIEWER>_<K>.json`, a JSON list. Each item has
`id`, `drug`, `disease`, `fda_indications` (indication text unioned across every label of the
drug's substance; `fda_combo_only` is true when all of it comes from combination products),
`fda_contraindications`, `fda_warnings` (only for FP3 checks) and `ema_indications`. Empty
strings mean we hold no text from that regulator — judge from whatever is present; FDA and
EMA are a union, so a TARGET in either is TARGET.

You do not know which resource asserted an edge or which release it came from, and you must
not guess: judge only from the supplied text and standard medical synonymy. Do not use outside
knowledge of what the drug could treat.

Output: write `experiments/out/v2/claude<ROUND>_<REVIEWER>_<K>.json`, a JSON list with one
object per input item, in input order:
`{"id": ..., "verdict": <one rubric verdict>, "quote": <the deciding label phrase, verbatim, ≤ 200 chars, or "">, "note": <one sentence of reasoning>}`.
Every input id must appear exactly once. Do not skip items; use `UNSURE` only as the rubric
allows.

Reviewer B additionally: be adversarial. For every edge, actively look for the reading under
which it is *not* a genuine target (population vs target, symptom vs disease, combination
partner, negation, over-broad parent) before accepting TARGET; still follow the rubric, and
still call TARGET when the text supports it.

Tie-breaker: input items carry `reviewer_1` and `reviewer_2` (verdict, quote, note). Decide
independently from the text, then use the two readings only to make sure you have
considered both; output the same shape as a reviewer (`tiebreak<ROUND>_<K>.json`).

Co-ingredient check: input items carry `single_ingredient_indications` and
`combination_product_indications` separately. The edge was judged TARGET on the union.
Output `TARGET` if the single-ingredient text (or EMA text) supports the indication, or the
combination text attributes it to this drug's own component; output `FP6_coingredient` if
the indication appears only on combination labels and belongs to a partner ingredient (or
cannot be attributed to this drug); `UNSURE` otherwise (`combo<ROUND>_check_<K>.json`).
