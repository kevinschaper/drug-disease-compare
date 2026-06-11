export default {
  title: "MEDIC ↔ Drug Approvals KP",
  root: "src",
  theme: ["air", "near-midnight"],
  // (pairs.parquet is registered per-page via `sql` front matter, where the
  // path is page-relative — see src/drug.md, src/disease.md, src/diff.md.)
  // Drop Inputs.table's selection checkbox column site-wide (we link rows out
  // to detail pages instead of selecting them in place).
  head: '<style>table td:has(> input[type="checkbox"]), table th:has(> input[type="checkbox"]) { display: none; }</style>',
  pages: [
    {name: "Overview", path: "/"},
    {name: "Drug coverage", path: "/drugs"},
    {name: "Disease coverage", path: "/diseases"},
    {name: "Disagreements", path: "/diff"},
    {name: "De-conflation", path: "/deconflation"},
    {name: "Contraindications", path: "/contraindications"},
    {name: "Methods", path: "/methods"},
  ],
  header: "MEDIC ↔ Drug Approvals KP — hierarchy-aware drug→disease edge comparison",
  footer:
    'Compares Monarch <code>medic-ingest</code> indication edges against the ' +
    'Multiomics <code>Drug Approvals KP</code>, reconciled MONDO-centrically via ' +
    'SRI Node Normalizer cliques.',
  toc: true,
};
