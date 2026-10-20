#!/usr/bin/env python3
"""Fetch URLs into evidence/ and append one log row per request.

Usage:
    python3 scripts/fetch.py <batch> <urlfile>

`<urlfile>` holds one URL per line, `#` comments and blank lines ignored.
Each URL is written to `evidence/<batch>/<nnn>_<slug>.body` and one row is
appended to `evidence/fetchlog.tsv` with:

    batch  code  bytes  sha256  elapsed_ms  content_type  url  path

The body is written even when the response is an error, so a 404 or a 403 is
an artefact that can be read rather than a gap. A transport failure (DNS,
timeout, TLS) writes no body and records code 000.

Deliberate choices, all of them recorded in the report:
  - no API key is sent, so every captured allowance is the anonymous one;
  - the User-Agent names the project, so a provider that blocks it blocks it
    visibly in the log rather than silently;
  - --max-time bounds every request so nothing hangs the batch.
"""
import hashlib
import os
import re
import subprocess
import sys
import time

UA = "Mozilla/5.0 (compatible; ar-6f2d90-research-bot; +https://github.com/talaria0101/ar-6f2d90)"
TIMEOUT = 45


def slug_for(url):
    s = re.sub(r"^https?://", "", url)
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")[:120]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, outdir, index, batch):
    path = os.path.join(outdir, "%03d_%s.body" % (index, slug_for(url)))
    hdr = path + ".headers"
    cmd = [
        "curl", "-sS", "-L", "--max-time", str(TIMEOUT),
        "-A", UA,
        "-H", "Accept: */*",
        "-D", hdr,
        "-o", path,
        "-w", "%{http_code}\\t%{size_download}\\t%{time_total}\\t%{content_type}\\t%{url_effective}",
        url,
    ]
    t0 = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 15)
        out = res.stdout.strip()
    except subprocess.TimeoutExpired:
        out = "000\t0\t0\t-\t-"
    if not os.path.exists(path):
        open(path, "wb").close()
        code, size, elapsed, ctype, eff = ("000", "0", "0", "-", "-")
        if out.count("\t") >= 4:
            parts = out.split("\t")
            code = parts[0]
        os.unlink(hdr) if os.path.exists(hdr) else None
    else:
        parts = out.split("\t")
        if len(parts) >= 5:
            code, size, elapsed, ctype, eff = parts[0], parts[1], parts[2], parts[3], parts[4]
        else:
            code, size, elapsed, ctype, eff = ("000", "0", "0", "-", "-")
        if os.path.exists(hdr):
            os.unlink(hdr)
    nbytes = os.path.getsize(path)
    digest = sha256_file(path)
    elapsed_ms = int(float(elapsed) * 1000) if elapsed.replace(".", "", 1).isdigit() else 0
    row = "\t".join([batch, code, str(nbytes), digest, str(elapsed_ms), ctype or "-", url, path])
    print(row)
    return row


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    batch = sys.argv[1]
    urlfile = sys.argv[2]
    outdir = os.path.join("evidence", batch)
    os.makedirs(outdir, exist_ok=True)
    urls = []
    with open(urlfile, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    logpath = os.path.join("evidence", "fetchlog.tsv")
    new = not os.path.exists(logpath)
    with open(logpath, "a", encoding="utf-8") as log:
        if new:
            log.write("batch\tcode\tbytes\tsha256\telapsed_ms\tcontent_type\turl\tpath\n")
        for i, url in enumerate(urls, 1):
            row = fetch(url, outdir, i, batch)
            log.write(row + "\n")
            log.flush()


if __name__ == "__main__":
    main()
