#!/usr/bin/env python3
"""Capture documentation pages and probe llms.txt for every service.

Usage: python3 scripts/capture_docs.py

Reads data/service_map.tsv and, for each service:
  1. fetches its docs URL into evidence/docs/<nnn>_<slug>.body
  2. probes https://<home-host>/llms.txt and records whether the response is
     a markdown index served by that host

The llms.txt test follows the reference inventory's rule: a file counts only
when it is markdown served by the provider's own domain. A 200 that returns an
HTML page, a robots-style rules file, or a redirect to a third-party docs host
is recorded as a rejection with the reason, not as a pass.

Writes evidence/docs/index.tsv and data/llms.json.
"""
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

UA = "Mozilla/5.0 (compatible; ar-6f2d90-research-bot; +https://github.com/talaria0101/ar-6f2d90)"
TIMEOUT = 40


def slug_for(s):
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")[:80]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def curl(url, path, cap="4000000"):
    cmd = ["curl", "-sS", "-L", "--max-time", str(TIMEOUT), "--max-filesize", cap,
           "-A", UA, "-o", path,
           "-w", "%{http_code}\t%{time_total}\t%{content_type}\t%{url_effective}", url]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 20)
        parts = res.stdout.strip().split("\t")
        if len(parts) >= 4:
            return parts[0], parts[1], parts[2], parts[3]
    except subprocess.TimeoutExpired:
        pass
    return "000", "0", "-", "-"


# Hosts that serve a generic platform llms.txt which does not describe the
# service being probed. GitHub serves https://github.com/llms.txt for every
# repository path, so a docs link on github.com resolves to GitHub's own file.
# That body passed every other test in the reference inventory and is the
# known false-positive shape, so it is rejected explicitly.
PLATFORM_HOSTS = {"github.com", "raw.githubusercontent.com", "gitbook.io",
                  "readme.io", "medium.com", "notion.so"}


def is_llms_md(body, final_url, home_host):
    """Return (ok, reason) for a candidate llms.txt body."""
    if not body.strip():
        return False, "empty-body"
    host = urlparse(final_url).hostname or ""
    if host != home_host and not host.endswith("." + home_host) and home_host not in host:
        return False, "served-by-other-host:" + host
    # The body must name the service's own domain, not a platform's.
    for p in PLATFORM_HOSTS:
        if host == p or host.endswith("." + p):
            return False, "platform-llms:" + host
    head = body[:400].lower()
    if head.startswith("<!doctype html") or head.startswith("<html") or "<head>" in head:
        return False, "html-not-markdown"
    if head.startswith("user-agent:") or "disallow:" in head:
        return False, "robots-rules"
    if not body.lstrip().startswith("#"):
        return False, "no-markdown-heading"
    if "]" not in body or "(" not in body:
        return False, "no-link-index"
    return True, "markdown-index"


def work(args):
    i, svc = args
    outdir = "evidence/docs"
    slug = slug_for(svc["service"])
    path = os.path.join(outdir, "%03d_%s.body" % (i, slug))
    code, elapsed, ctype, eff = curl(svc["docs"], path)
    if not os.path.exists(path):
        open(path, "wb").close()
    row = [svc["service"], code, str(os.path.getsize(path)), sha256_file(path),
           str(int(float(elapsed) * 1000)) if re.match(r"^[0-9.]+$", elapsed) else "0",
           ctype or "-", svc["docs"], path]

    # llms.txt probe. Two hosts are tried, because a service routinely
    # publishes its docs on a subdomain and its llms.txt there: OpenAlex
    # serves one at help.openalex.org and returns 403 at the apex. The first
    # host whose body passes the markdown-index test wins; the other attempt
    # is kept in the record so a rejection is visible.
    home_host = urlparse(svc["home"]).hostname or ""
    docs_host = urlparse(svc["docs"]).hostname or ""
    hosts = [home_host] + ([docs_host] if docs_host and docs_host != home_host else [])
    attempts = []
    chosen = None
    for n, host in enumerate(hosts):
        lpath = os.path.join(outdir, "%03d_%s.llms%s.body" % (i, slug, "" if n == 0 else "_docs"))
        lurl = "https://%s/llms.txt" % host
        lcode, lelapsed, lctype, leff = curl(lurl, lpath, cap="2000000")
        if not os.path.exists(lpath):
            open(lpath, "wb").close()
        with open(lpath, encoding="utf-8", errors="replace") as fh:
            lbody = fh.read()
        ok, reason = is_llms_md(lbody, leff, host) if lcode == "200" else (False, "http-" + lcode)
        attempt = {"host": host, "url": lurl, "code": lcode, "ok": ok,
                   "reason": reason, "final_url": leff, "path": lpath,
                   "bytes": os.path.getsize(lpath), "sha256": sha256_file(lpath)}
        attempts.append(attempt)
        if ok and chosen is None:
            chosen = attempt
    llms = {"service": svc["service"], "ok": chosen is not None,
            "url": (chosen or attempts[0])["url"],
            "code": (chosen or attempts[0])["code"],
            "bytes": (chosen or attempts[0])["bytes"],
            "reason": "markdown-index" if chosen else attempts[0]["reason"],
            "path": (chosen or attempts[0])["path"],
            "sha256": (chosen or attempts[0])["sha256"],
            "attempts": attempts}
    return row, llms


def main():
    os.makedirs("evidence/docs", exist_ok=True)
    with open("data/service_map.tsv", encoding="utf-8") as fh:
        services = list(csv.DictReader(fh, delimiter="\t"))
    jobs = list(enumerate(services, 1))
    rows, llms = [], []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for row, l in ex.map(work, jobs):
            rows.append(row)
            llms.append(l)
            print("%-30s docs=%s llms=%s %s" % (row[0], row[1], l["code"], l["reason"]))
    with open("evidence/docs/index.tsv", "w", encoding="utf-8") as fh:
        fh.write("service\tcode\tbytes\tsha256\telapsed_ms\tcontent_type\turl\tpath\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    with open("data/llms.json", "w", encoding="utf-8") as fh:
        json.dump(llms, fh, indent=1)
    # Count distinct hosts, not endpoints: six DataCite endpoints share one
    # llms.txt at support.datacite.org, and counting it six times would
    # overstate how widely the convention is adopted.
    from urllib.parse import urlparse as _up
    ok_hosts = {_up(l["url"]).hostname for l in llms if l["ok"]}
    probed_hosts = {_up(l["url"]).hostname for l in llms}
    print("\n%d docs captures, %d hosts publish a verified llms.txt of %d hosts probed"
          " (%d endpoints) -> evidence/docs/index.tsv"
          % (len(rows), len(ok_hosts), len(probed_hosts), len(llms)))
    for h in sorted(ok_hosts):
        print("  verified: %s" % h)


if __name__ == "__main__":
    main()
