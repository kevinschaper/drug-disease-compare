// "Label check" chips for the drug & disease detail pages: an automated screen (the Jev
// decision model, confidence >= 0.9 only) of each source's pair against independently
// fetched FDA/EMA label text. Each chip gets a plain-language hover card.
import {html} from "npm:htl";

const SOURCE = {medic: "MEDIC", "dakp-approved": "DAKP (approved)"};

// verdict -> [short chip label, type name, plain-language explanation]
const VERDICT = {
  TARGET: ["✓", "genuine indication", "The label text supports this as a genuine indication: the drug is indicated to treat, prevent or manage this disease (or a more specific form of an indicated condition)."],
  FP1_setting: ["⚠ setting", "setting as target", "The disease appears in the label only as the patient population or background (e.g. \"reduce the risk of MI in patients with coronary heart disease\"), not as what the drug treats."],
  FP2_symptom_swap: ["⚠ symptom", "symptom ↔ disease swap", "The label treats a symptom or manifestation, and the edge names the underlying disease instead (or the reverse)."],
  FP3_cross_section: ["⚠ warning only", "cross-section bleed", "The disease appears only in the label's contraindications or warnings, not in its indications."],
  FP4_overbroad: ["⚠ too broad", "over-broad", "The edge names a whole disease class much broader than the specific condition the label indicates (e.g. label \"metastatic breast cancer\", edge \"cancer\")."],
  FP5_negation: ["⚠ negated", "negation", "The label says the drug is not indicated, not established, or not recommended for this disease."],
  FP6_coingredient: ["⚠ co-ingredient", "co-ingredient attribution", "The indication is on a combination product's label and belongs to the other ingredient, not this drug."],
  FP7_notintext: ["⚠ not in label", "not in label", "Neither the disease nor a synonym, subtype or close parent appears in the label text; usually a term-mapping artifact."],
};

let tip;
function tooltip() {
  if (tip?.isConnected) return tip;
  tip = document.createElement("div");
  tip.className = "lc-tip";
  document.body.appendChild(tip);
  return tip;
}

function show(anchor, c) {
  const t = tooltip();
  const [, title, explain] = VERDICT[c.verdict] ?? ["", c.verdict, ""];
  t.replaceChildren(html`<div class="lc-tip-head">${SOURCE[c.source] ?? c.source} · ${c.verdict === "TARGET" ? "label supports it" : `likely error: ${title}`}</div>
    <div>${explain}</div>
    <div class="lc-tip-foot">Automated label check (Jev decision model), confidence ${(c.confidence * 100).toFixed(0)}%.
      Only verdicts at ≥ 90% confidence are shown; on a reviewed sample, about 9 in 10 such flags
      held up. A lead to check, not a verdict (method: the Error taxonomy page).</div>`);
  t.classList.add("show");
  const r = anchor.getBoundingClientRect();
  const {width: w, height: h} = t.getBoundingClientRect();
  t.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
  t.style.top = (r.bottom + 6 + h > window.innerHeight - 8 ? r.top - h - 6 : r.bottom + 6) + "px";
}

function hide() {
  tip?.classList.remove("show");
}

// one cell: a chip per source that has a confident verdict for this pair
export function labelCheckCell(checks) {
  if (!checks?.length) return "";
  return html`${checks.map((c) => {
    const [short] = VERDICT[c.verdict] ?? [c.verdict];
    const chip = html`<span class="lc ${c.verdict === "TARGET" ? "lc-ok" : "lc-fp"}" tabindex="0">${c.source === "medic" ? "MEDIC" : "DAKP"} ${short}</span>`;
    chip.addEventListener("mouseenter", () => show(chip, c));
    chip.addEventListener("focus", () => show(chip, c));
    chip.addEventListener("mouseleave", hide);
    chip.addEventListener("blur", hide);
    return chip;
  })}`;
}

export const labelCheckStyle = html`<style>
.lc { display: inline-block; font-size: 11px; padding: 0 5px; margin: 0 3px 2px 0; border-radius: 4px;
  white-space: nowrap; cursor: help; }
.lc-ok { background: color-mix(in srgb, #3a7d34 18%, transparent); }
.lc-fp { background: color-mix(in srgb, #b4423a 22%, transparent); font-weight: 600; }
.lc-tip { position: fixed; z-index: 1000; max-width: 360px; padding: 8px 10px; border-radius: 6px;
  font: 12px/1.45 var(--sans-serif, system-ui); background: var(--theme-background-alt, #fff);
  color: var(--theme-foreground, #1b1e23); border: 1px solid var(--theme-foreground-faint, #ccc);
  box-shadow: 0 4px 14px rgba(0,0,0,.15); display: none; pointer-events: none; }
.lc-tip.show { display: block; }
.lc-tip-head { font-weight: 700; margin-bottom: 3px; }
.lc-tip-foot { margin-top: 6px; color: var(--theme-foreground-muted, #6b7280); font-size: 11px; }
</style>`;
