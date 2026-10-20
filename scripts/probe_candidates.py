#!/usr/bin/env python3
"""Probe every candidate's api_probe URL and record what came back.

Usage: python3 scripts/probe_candidates.py data/candidates.tsv

Writes evidence/probe/<batch>/<nnn>_<slug>.body plus one row per probe to
evidence/probe/index.tsv. Runs a small thread pool so the whole set finishes
in a couple of minutes; each request still carries its own timeout.

A probe is evidence of reachability and of the shape of the anonymous
response. It is not evidence of an allowance: the allowance claim in
data/providers.tsv comes from the docs capture, separately.
"""
import csv
import hashlib
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (compatible; ar-6f2d90-research-bot; +https://github.com/talaria0101/ar-6f2d90)"
TIMEOUT = 40
BATCH = os.environ.get("PROBE_BATCH", "probe")


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


def probe(args):
    idx, slug, url = args
    outdir = os.path.join("evidence", BATCH)
    path = os.path.join(outdir, "%03d_%s.body" % (idx, slug_for(url)))
    cmd = [
        "curl", "-sS", "-L", "--max-time", str(TIMEOUT), "-A", UA,
        "-o", path,
        "-w", "%{http_code}\\t%{time_total}\\t%{content_type}",
        url,
    ]
    code, elapsed, ctype = "000", "0", "-"
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 20)
        parts = res.stdout.strip().split("\t")
        if len(parts) >= 3:
            code, elapsed, ctype = parts[0], parts[1], parts[2]
    except subprocess.TimeoutExpired:
        pass
    if not os.path.exists(path):
        open(path, "wb").close()
    nbytes = os.path.getsize(path)
    digest = sha256_file(path)
    ms = int(float(elapsed) * 1000) if re.match(r"^[0-9.]+$", elapsed or "") else 0
    return [slug, code, str(nbytes), digest, str(ms), ctype or "-", url, path]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/candidates.tsv"
    with open(src, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    os.makedirs(os.path.join("evidence", BATCH), exist_ok=True)
    jobs = [(i, r["slug"], r["api_probe"]) for i, r in enumerate(rows, 1)]
    t0 = time.time()
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(probe, jobs):
            out.append(res)
            print("\t".join(res[:6]))
    out.sort(key=lambda r: r[0])
    with open(os.path.join("evidence", BATCH, "index.tsv"), "w", encoding="utf-8") as fh:
        fh.write("slug\tcode\tbytes\tsha256\telapsed_ms\tcontent_type\turl\tpath\n")
        for r in out:
            fh.write("\t".join(r) + "\n")
    print("\n%d probes in %.0fs -> evidence/%s/index.tsv" % (len(out), time.time() - t0, BATCH))


if __name__ == "__main__":
    main()
