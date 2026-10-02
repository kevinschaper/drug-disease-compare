# Indication audit rubric (v2)

You are judging one asserted edge: **"DRUG is indicated for DISEASE"** — i.e. DISEASE is a
genuine treatment / prevention / management *target* of DRUG according to the regulator
text supplied (FDA label indications and/or EMA EPAR therapeutic indication). Judge **only
from the supplied text**; it was fetched independently of the source that made the claim.
Use standard medical synonyms (e.g. "high blood pressure" = hypertension, "CIC" = chronic
idiopathic constipation) but do not use outside knowledge of what the drug *could* treat.

Pick exactly one verdict.

| Verdict | Meaning |
|---|---|
| `TARGET` | The indication text names DISEASE (or an exact synonym) as something the drug treats, prevents, or manages. **Also TARGET** when DISEASE is a *subtype* or *more specific form* of an indicated condition (label: "hypertension" → edge: "essential hypertension"), or a named item in a list of indicated conditions. Adjunctive / combination-therapy indications still count. |
| `FP1_setting` | DISEASE appears in the indication only as the **setting, population or background**, not the thing treated: e.g. "reduce the risk of MI *in patients with* coronary heart disease" → edge "coronary heart disease"; "diagnostic agent for adrenal insufficiency" → edge "adrenal insufficiency"; "prophylaxis of nausea *in patients receiving chemotherapy*" → edge "cancer"; supportive care where DISEASE is the underlying illness. |
| `FP2_symptom_swap` | The text treats a **symptom / manifestation**, and the edge names the underlying disease instead (or the reverse): e.g. "relief of nasal congestion due to the common cold" → edge "common cold"; "pain of osteoarthritis" judged against edge "osteoarthritis" is **TARGET** (management of the disease's pain counts), so use FP2 only when the text clearly treats a symptom *rather than* the disease. |
| `FP3_cross_section` | DISEASE appears in the supplied text **only outside the indications** — contraindications, warnings, adverse reactions, drug interactions — and not as an indication. |
| `FP4_overbroad` | The edge's DISEASE is a **broader parent** than what is indicated, broad enough that the claim is misleading at that level: e.g. label "metastatic breast cancer" → edge "cancer"; label "acute lymphoblastic leukemia" → edge "hematologic disease". Call FP4 only when the parent is a whole disease class or organ-system category. A near parent that still essentially describes what's indicated (label lists aspergillosis, candidemia and other fungal infections → edge "fungal infectious disease") is **TARGET**. |
| `FP5_negation` | The text explicitly says the drug is **not** indicated / not established / not recommended for DISEASE (limitations of use, "not indicated for", "safety and effectiveness not established in"). |
| `FP6_coingredient` | DISEASE is indicated only on a **combination product** label, and the indication belongs to the *other* ingredient(s), not DRUG (e.g. atorvastatin → hypertension via the amlodipine/atorvastatin combination). |
| `FP7_notintext` | DISEASE (or a synonym / subtype / parent at reasonable granularity) is **not mentioned anywhere** in the supplied text and no reasonable reading supports it — a spurious mapping (e.g. acronym collision: "MCL" mast-cell leukemia vs mantle-cell lymphoma). |
| `UNSURE` | The text is too fragmentary or ambiguous to decide (e.g. it's an empty header, or about a different product entirely). |

Rules of thumb:
- **Granularity favours TARGET when the edge is narrower** than the label, **FP4 when it is
  much broader**.
- If the drug is indicated for DISEASE in *one* of the supplied texts (FDA or EMA), it's
  TARGET — the texts are a union.
- **Combination products:** an indication on a fixed-dose combination label counts for DRUG
  only if it is attributable to DRUG's own component. If it belongs to the *partner*
  ingredient (amlodipine/atorvastatin → hypertension is amlodipine's), it's
  `FP6_coingredient`. *(Added after round 1: the first rater round followed an earlier rule
  that credited every combination indication; a dedicated co-ingredient check re-judged
  every TARGET whose evidence included combination labels.)*
- Prefer a specific FP type over `FP7` whenever DISEASE *is* mentioned (as setting,
  symptom, contraindication, negation, or child).
