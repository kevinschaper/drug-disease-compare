// Source-bucket helpers shared by the drug & disease detail pages.
// A pair's membership is split into four buckets (DAKP is split by approval status),
// computed from the per-source exact membership the pipeline already emits.
export const APPROVED = "approved_for_condition";
export const OFFLABEL = "off_label_use";
export const BUCKETS = ["MEDIC", "DAKP-approved", "DAKP off-label", "dismech"];

// Which buckets a detail row belongs to (exact membership only; "related" is a
// hierarchy note, shown in columns, not a bucket).
export function bucketsOf(r) {
  const b = [];
  if (r.medic === "exact") b.push("MEDIC");
  if (r.dakp === "exact" && r.dakp_status === APPROVED) b.push("DAKP-approved");
  if (r.dakp === "exact" && r.dakp_status === OFFLABEL) b.push("DAKP off-label");
  if (r.dismech === "exact") b.push("dismech");
  return b;
}

// The exact source-combination key (UpSet cell) — an EXCLUSIVE set, so single-source
// groups are suffixed "only" to distinguish "DAKP-approved only" (this group) from the
// DAKP-approved bucket total (which is spread across every group containing it).
export function comboKey(r) {
  const b = bucketsOf(r);
  if (!b.length) return "(related only)";
  return b.length === 1 ? `${b[0]} only` : b.join(" + ");
}

// per-bucket counts across rows (a row can fall in several buckets)
export function bucketCounts(rows) {
  const c = new Map(BUCKETS.map((b) => [b, 0]));
  for (const r of rows) for (const b of bucketsOf(r)) c.set(b, c.get(b) + 1);
  return c;
}

// counts per exact combination. DAKP off-label is expected noise, so any combination
// involving it sorts to the bottom regardless of size; everything else is biggest-first.
export function comboCounts(rows) {
  const m = new Map();
  for (const r of rows) {
    const k = comboKey(r);
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  const offlabelLast = (k) => (k.includes("DAKP off-label") ? 1 : 0);
  return [...m].sort((a, b) =>
    offlabelLast(a[0]) - offlabelLast(b[0]) || b[1] - a[1] || a[0].localeCompare(b[0]));
}
