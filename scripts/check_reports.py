#!/usr/bin/env python3
"""Verify every claim in data/providers.tsv against the captured artefacts.

Usage: python3 scripts/check_reports.py

Checks, one line per failure, exit 1 if any fail:

  1. every probe_slug exists in evidence/verdicts.tsv
  2. that row's verdict is `payload`
  3. the evidence_path exists on disk
  4. the recorded sha256 equals the file's sha256
  5. the recorded byte count equals the file's size
  6. the recorded `observed` figure is recomputed from the body by
     scripts/observe_lib.py and must match exactly
  7. no service appears twice
  8. category and auth values are from the allowed sets
  9. every row in data/service_map.tsv appears in data/providers.tsv and back
 10. every table row in report/01-providers.md names a service in the TSV
 11. every docs capture in evidence/docs/index.tsv that returned 200 has a body
     whose digest matches its index row

Check 6 is the one that matters. Checks 4 and 5 prove the file is the file.
Check 6 proves the number in the report was computed from the bytes, because
the checker recomputes it with the same function the report used, and a
mismatch between the two would mean the report had been hand-edited.

The checker deliberately shares the extractor's implementation rather than
re-deriving the rule. An independent re-derivation drifted once already (the
extractor counted one <PubmedArticle> element; a hand-written checker counted
19 lines), and a verifier that disagrees with the producer about the rule
cannot tell a wrong figure from a differently-defined right one.
"""
import csv
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from observe_lib import observe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATEGORIES = {"academic", "archive"}
AUTH_VALUES = {"none", "key-optional", "key-required", "demo-key", "email-required"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main():
    os.chdir(ROOT)
    errors = []
    providers = read_tsv("data/providers.tsv")
    verdicts = {r["slug"]: r for r in read_tsv("evidence/verdicts.tsv")}
    service_map = read_tsv("data/service_map.tsv")

    seen = set()
    for p in providers:
        svc = p["service"]
        if svc in seen:
            errors.append("%s: duplicate service" % svc)
        seen.add(svc)

        if p["category"] not in CATEGORIES:
            errors.append("%s: category %r not allowed" % (svc, p["category"]))
        if p["auth"] not in AUTH_VALUES:
            errors.append("%s: auth %r not allowed" % (svc, p["auth"]))

        slug = p["probe_slug"]
        v = verdicts.get(slug)
        if v is None:
            errors.append("%s: probe_slug %r not in evidence/verdicts.tsv" % (svc, slug))
            continue
        if v["verdict"] != "payload":
            errors.append("%s: probe %r verdict is %r, not payload" % (svc, slug, v["verdict"]))
            continue

        path = p["evidence_path"]
        if not os.path.exists(path):
            errors.append("%s: evidence_path missing: %s" % (svc, path))
            continue
        if sha256(path) != p["sha256"]:
            errors.append("%s: sha256 mismatch for %s" % (svc, path))
        if str(os.path.getsize(path)) != p["bytes"]:
            errors.append("%s: bytes %s != file size %d" %
                          (svc, p["bytes"], os.path.getsize(path)))

        with open(path, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
        recomputed = observe(body, path)
        if recomputed != p["observed"]:
            errors.append("%s: observed %r but body yields %r" %
                          (svc, p["observed"], recomputed))

    mapped = {r["service"] for r in service_map}
    for svc in sorted(mapped - seen):
        errors.append("%s: in service_map.tsv but not in providers.tsv" % svc)
    for svc in sorted(seen - mapped):
        errors.append("%s: in providers.tsv but not in service_map.tsv" % svc)

    report = "report/01-providers.md"
    if os.path.exists(report):
        with open(report, encoding="utf-8") as fh:
            text = fh.read()
        named = set()
        for line in text.splitlines():
            if line.startswith("| ") and not line.startswith("|--"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 3:
                    named.add(cells[1])
        for svc in sorted(seen):
            if svc not in named:
                errors.append("%s: not in %s" % (svc, report))
    else:
        errors.append("report/01-providers.md missing")

    # A `demo-key` row claims the published demo key is load-bearing. That
    # claim is only true if the same endpoint refuses with no credential, so
    # the no-key capture must exist and must not be a payload.
    demo = [r for r in providers if r["auth"] == "demo-key"]
    if demo:
        nokey_dir = "evidence/nokey"
        if not os.path.isdir(nokey_dir):
            errors.append("demo-key rows exist but %s is missing" % nokey_dir)
        else:
            bodies = [f for f in os.listdir(nokey_dir) if f.endswith(".body")]
            if not bodies:
                errors.append("demo-key rows exist but no no-key capture was made")
            for f in bodies:
                path = os.path.join(nokey_dir, f)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
                try:
                    import json as _json
                    obj = _json.loads(text)
                    is_payload = isinstance(obj, dict) and "response" in obj
                except Exception:
                    is_payload = False
                if is_payload:
                    errors.append("%s: captured a payload without a key, so the "
                                  "demo-key label is wrong" % path)

    docs_index = "evidence/docs/index.tsv"
    if os.path.exists(docs_index):
        for row in read_tsv(docs_index):
            path = row["path"]
            if not os.path.exists(path):
                errors.append("docs capture missing: %s" % path)
                continue
            if sha256(path) != row["sha256"]:
                errors.append("docs capture digest mismatch: %s" % path)

    if errors:
        print("FAIL (%d problems)" % len(errors))
        for e in errors:
            print("  - " + e)
        return 1
    print("PASS: %d endpoints, %d providers, %d docs captures, every figure "
          "recomputed from the captured bytes"
          % (len(providers), len({r["provider"] for r in service_map}),
             len(read_tsv(docs_index)) if os.path.exists(docs_index) else 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
