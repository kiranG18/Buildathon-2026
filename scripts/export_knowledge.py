"""One-time export of the prototype's knowledge documents to markdown files with frontmatter.

Chunk ids stay pinned with <!-- K-xxx --> markers so citations in seeded messages keep resolving.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

METADATA = {
    "case study": {"quality": "high"},
    "examples": {"quality": "high"},
}


def main() -> None:
    d = json.loads((ROOT / "seed" / "prototype_state.json").read_text(encoding="utf-8"))
    ktext = d["KTEXT"]
    for doc_id, name, doc_type, scope, chunk_ids in d["KDOCS"]:
        folder = "global" if scope == "G" else scope.lower()
        out = ROOT / "knowledge" / folder / f"{doc_id.lower()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        fm = ["---", f"id: {doc_id}", f"name: {name}", f"doc_type: {doc_type}", f"scope: {'global' if scope == 'G' else scope}"]
        for k, v in METADATA.get(doc_type, {}).items():
            fm.append(f"{k}: {v}")
        fm.append("---")
        body = "\n\n".join(f"<!-- {cid} -->\n{ktext[cid]}" for cid in chunk_ids)
        out.write_text("\n".join(fm) + "\n\n" + body + "\n", encoding="utf-8")
    print("wrote", len(d["KDOCS"]), "documents")


if __name__ == "__main__":
    main()
