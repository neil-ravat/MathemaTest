"""Download pinned OpenStax CNXML and preserve source order and MathML.

This reconstructs a new corpus, not the missing original experiment dataset.
Run from the repository root: .venv/bin/python scripts/prepare_openstax.py
"""
import hashlib
import copy
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone

REVISION = "8dbc2ce19e804924b2517b89ac72ee45be949d15"
REPOSITORY = "https://github.com/openstax/osbooks-calculus-bundle"
RAW = f"https://raw.githubusercontent.com/openstax/osbooks-calculus-bundle/{REVISION}/"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/openstax_calculus_v1"
CN = "{http://cnx.rice.edu/cnxml}"
COL = "{http://cnx.rice.edu/collxml}"
MATH = "{http://www.w3.org/1998/Math/MathML}"
MD = "{http://cnx.rice.edu/mdml}"


def download(path):
    target = DEST / "source" / path
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(RAW + path, timeout=45) as response:
                    data = response.read()
                temp = target.with_suffix(target.suffix + ".tmp")
                temp.write_bytes(data)
                temp.replace(target)
                break
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
    data = target.read_bytes()
    return {"path": path, "url": RAW + path, "sha256": hashlib.sha256(data).hexdigest()}


def render(node, unsupported):
    """Readable math for retrieval; original XML remains the source of truth."""
    tag = node.tag.split("}")[-1]
    children = [render(c, unsupported) for c in node]
    if node.tag.startswith(MATH):
        if tag == "mtable":
            # Keep row/cell boundaries: concatenation can turn distinct rules
            # into one false equation. Spanning/layout-dependent cells stay gated.
            if any(n.get(a, "1") != "1" for n in node.iter()
                   for a in ("rowspan", "columnspan")):
                unsupported.add("spanned-mtable")
            return " table[ " + " ; ".join(children) + " ] "
        if tag in {"mtr", "mlabeledtr"}:
            return "row[ " + " | ".join(children) + " ]"
        if tag == "mtd":
            return (node.text or "") + "".join(children)
        if tag == "mfrac" and len(children) == 2:
            return f"(({children[0]})/({children[1]}))"
        if tag in ("msup", "msub") and len(children) == 2:
            op = "^" if tag == "msup" else "_"
            return f"({children[0]}){op}({children[1]})"
        if tag == "msubsup" and len(children) == 3:
            return f"({children[0]})_({children[1]})^({children[2]})"
        if tag == "msqrt":
            return "sqrt(" + "".join(children) + ")"
        if tag == "mroot" and len(children) == 2:
            return f"root({children[1]}, {children[0]})"
        if tag in ("munder", "mover", "munderover"):
            return tag + "(" + ", ".join(children) + ")"
        if tag == "mfenced":
            return node.get("open", "(") + ",".join(children) + node.get("close", ")")
        if tag not in {"math", "mrow", "mi", "mo", "mn", "mtext", "mstyle", "mspace"}:
            unsupported.add(tag)
        return (node.text or "") + "".join(children)
    if tag == "link" and node.get("target-id"):
        return f" [reference:{node.get('document', '')}#{node.get('target-id')}] "
    if tag in {"figure", "media", "image"}:
        return " [unrendered-media] "
    if tag == "table":
        if any(n.get(a) for n in node.iter() for a in ("namest", "nameend", "morerows")):
            unsupported.add("spanned-cnxml-table")
        return " table[ " + " ; ".join(children) + " ] "
    if tag == "row":
        return "row[ " + " | ".join(children) + " ]"
    return (node.text or "") + "".join(t + (c.tail or "") for c, t in zip(node, children))


def extract_module(path, module_id, chapter, module_order, start):
    tree = ET.parse(path).getroot()
    title = tree.findtext(CN + "title", default="")
    content = tree.find(CN + "content")
    records = []
    blocks = {"para", "equation", "note", "rule", "definition", "example", "exercise"}

    def visit(node):
        kind = node.tag.split("}")[-1]
        if kind not in blocks:
            for child in node:
                visit(child)
            return
        # Do not supply an exercise's answer as its statement.
        body = node.find(CN + "problem") if kind == "exercise" else node
        if body is None:
            return
        unsupported = set()
        text = re.sub(r"\s+", " ", render(body, unsupported)).strip()
        if not text:
            return
        position = start + len(records)
        anchor = node.get("id", f"block-{position}")
        label = node.findtext(CN + "title", default="")
        mathml = []
        for original in body.iter(MATH + "math"):
            math = copy.deepcopy(original)
            math.tail = None
            mathml.append(ET.tostring(math, encoding="unicode"))
        records.append({
            "id": f"{module_id}:{anchor}", "content": text,
            "source_id": "openstax-calculus-v1-" + REVISION[:12],
            "chapter": chapter, "module_order": module_order, "position": position,
            "module_id": module_id, "module_title": title, "anchor": anchor,
            "kind": kind, "title": label,
            "is_target": kind in {"rule", "definition", "example", "exercise"} or
                         (kind == "note" and bool(re.search(r"definition|theorem", label, re.I))),
            "mathml": mathml,
            "unsupported_mathml": sorted(unsupported),
            "has_media": any(n.tag in {CN + "media", CN + "image", CN + "figure"} for n in body.iter()),
            "references": [{"module": l.get("document", module_id), "anchor": l.get("target-id")}
                           for l in body.iter(CN + "link") if l.get("target-id")],
            "source_url": RAW + f"modules/{module_id}/index.cnxml",
            "attribution": "OpenStax, Calculus Volume 1. Download for free at https://openstax.org/details/books/calculus-volume-1",
            "license": "CC-BY-NC-SA-4.0",
        })

    if content is not None:
        visit(content)
    return records


def main():
    collection = "collections/calculus-volume-1.collection.xml"
    sources = [download(p) for p in ("LICENSE", "README.md", collection)]
    tree = ET.parse(DEST / "source" / collection).getroot()
    modules = []
    chapter = 0
    for part in tree.find(COL + "content"):
        if part.tag == COL + "subcollection":
            chapter += 1
            modules.extend((n.get("document"), chapter) for n in part.iter(COL + "module"))
        elif part.tag == COL + "module":
            # Preface/appendices are stored but excluded from chapter evaluation.
            modules.append((part.get("document"), 0))
    paths = [f"modules/{mid}/index.cnxml" for mid, _ in modules]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item in pool.map(download, paths):
            sources.append(item)
            print("Downloaded", item["path"], flush=True)
    records = []
    for order, (mid, chapter) in enumerate(modules):
        records.extend(extract_module(DEST / "source" / paths[order], mid, chapter, order, len(records)))
    assert len({r['id'] for r in records}) == len(records), "Duplicate corpus IDs"
    output = DEST / "corpus.jsonl"
    output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    manifest = {"repository": REPOSITORY, "revision": REVISION,
                "built_at": datetime.now(timezone.utc).isoformat(),
                "license": tree.find('.//' + MD + "license").get("url"),
                "collection": collection, "modules": len(modules), "records": len(records),
                "by_chapter": dict(Counter(r['chapter'] for r in records)),
                "by_kind": dict(Counter(r['kind'] for r in records)),
                "unsupported_math_records": sum(bool(r['unsupported_mathml']) for r in records),
                "corpus_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source_files": sources,
                "limitations": ["New corpus, not original experiment data", "Not an independently labeled benchmark", "MathML rendering needs review; original markup preserved", "Media files are not downloaded; image-dependent cases need separate review", "Source references are not validated prerequisite edges"]}
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k:v for k,v in manifest.items() if k != 'source_files'}, indent=2))


if __name__ == "__main__":
    main()
