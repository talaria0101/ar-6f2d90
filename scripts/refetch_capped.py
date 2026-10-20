#!/usr/bin/env python3
"""Re-fetch specific probe URLs with a response size cap.

Usage: python3 scripts/refetch_capped.py <batch> <cap_bytes> <url> [url...]

Two captures in the first pass returned responses far too large to keep in a
repository (a Wayback TimeMap at 99 MB and an ACL Anthology .bib at 74 MB).
This script re-requests them with `--max-filesize`, which aborts the transfer
once the cap is exceeded. The stored body is then a truncated capture, and the
index row records it as such via the `truncated` marker in the slug column
suffix. The full response size is not recoverable from a capped request, so
the row records the cap rather than inventing a total.

Rewrites the matching row in evidence/<batch>/index.tsv.
"""
import csv
import hashlib
import os
import re
import subprocess
import sys

UA = "Mozilla/5.0 (compatible; ar-6f2d90-research-bot; +https://github.com/talaria0101/ar-6f2d90)"


def slug_for(url):
    s = re.sub(r"^https?://", "", url)
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")[:110]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    batch, cap = sys.argv[1], sys.argv[2]
    urls = sys.argv[3:]
    idx = os.path.join("evidence", batch, "index.tsv")
    with open(idx, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    fields = ["slug", "code", "bytes", "sha256", "elapsed_ms", "content_type", "url", "path"]
    by_url = {r["url"]: r for r in rows}
    for url in urls:
        row = by_url[url]
        path = row["path"]
        cmd = ["curl", "-sS", "-L", "--max-time", "60", "--max-filesize", cap,
               "-A", UA, "-o", path, "-w", "%{http_code}\\t%{time_total}\\t%{content_type}", url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        parts = res.stdout.strip().split("\t")
        code = parts[0] if len(parts) > 0 else "000"
        elapsed = parts[1] if len(parts) > 1 else "0"
        ctype = parts[2] if len(parts) > 2 else "-"
        if not os.path.exists(path):
            open(path, "wb").close()
        row["code"] = code
        row["bytes"] = str(os.path.getsize(path))
        row["sha256"] = sha256_file(path)
        row["elapsed_ms"] = str(int(float(elapsed) * 1000)) if re.match(r"^[0-9.]+$", elapsed) else "0"
        row["content_type"] = ctype + ";truncated-at-" + cap
        print("\t".join(row[f] for f in fields))
    with open(idx, "w", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
