export default {
  title: "drug-disease-compare",
  root: "src",
  theme: ["air", "near-midnight"],
  // (pairs.parquet is registered per-page via `sql` front matter, where the
  // path is page-relative — see src/drug.md, src/disease.md, src/diff.md.)
  head: `<style>
    /* Widen the content column on large screens so data tables get room. */
    :root { --observablehq-max-width: 1760px; }
    /* Drop Inputs.table's selection checkbox column site-wide (we link rows out
       to detail pages instead of selecting them in place). */
    table td:has(> input[type="checkbox"]),
    table th:has(> input[type="checkbox"]) { display: none; }
  </style>`,
  pages: [
    {name: "Overview", path: "/"},
    {name: "Drug coverage", path: "/drugs"},
    {name: "Disease coverage", path: "/diseases"},
    {name: "dismech lens", path: "/dismech"},
    {name: "Disagreements", path: "/diff"},
    {name: "Error taxonomy", path: "/error-taxonomy"},
    {name: "Off-label (FAERS)", path: "/offlabel"},
    {name: "De-conflation", path: "/deconflation"},
    {name: "Contraindications", path: "/contraindications"},
    {name: "Methods", path: "/methods"},
  ],
  header: "drug-disease-compare — hierarchy- and scope-aware cross-source drug→disease edges",
  footer:
    'Compares <code>MEDIC</code>, the <code>Drug Approvals KP</code>, and ' +
    '<code>dismech</code> drug→disease edges, reconciled MONDO-centrically via ' +
    'SRI Node Normalizer cliques.',
  toc: true,
};
