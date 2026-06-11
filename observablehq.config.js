export default {
  title: "MEDIC ↔ Drug Approvals KP",
  root: "src",
  theme: ["air", "near-midnight"],
  pages: [
    {name: "Overview", path: "/"},
    {name: "Drug coverage", path: "/drugs"},
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
