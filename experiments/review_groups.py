"""Dump every multi-member active_moiety group with a name-coherence flag, so all
merges can be eyeballed for over-merge after the ion guard. Run after drug_collapse."""
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def common_prefix(strs: list[str]) -> int:
    strs = [norm(s) for s in strs if s]
    if len(strs) < 2:
        return 0
    a, b = min(strs), max(strs)
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i


def main():
    a = json.load(open(OUT / "audit_active_moiety.json"))
    groups = a["groups"]
    print(f"active_moiety (guarded): {a['distinct_groups']} groups, "
          f"{a['multi_member_groups']} multi-member, {a['drugs_in_multi_groups']} drugs merged\n")
    coherent, review = [], []
    for g in groups:
        labels = sorted({m["label"] for m in g["members"]})
        (coherent if common_prefix(labels) >= 4 else review).append((g["group_label"], labels))
    print(f"== {len(review)} groups with NO shared name stem (eyeball for over-merge) ==")
    for gl, labels in sorted(review, key=lambda x: -len(x[1])):
        print(f"  [{len(labels)}] {gl}  <-  {', '.join(labels)}")
    print(f"\n== {len(coherent)} stem-coherent groups (likely same-drug salt/ester/stereo) ==")
    for gl, labels in sorted(coherent, key=lambda x: -len(x[1])):
        print(f"  [{len(labels)}] {gl}  <-  {', '.join(labels)}")


if __name__ == "__main__":
    main()
