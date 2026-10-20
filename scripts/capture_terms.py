#!/usr/bin/env python3
"""Capture the terms/rate-limit page for each provider and extract the sentence.

Usage: python3 scripts/capture_terms.py

For every provider in data/terms_urls.tsv:
  1. fetch the terms URL into evidence/terms/<nnn>_<slug>.body
  2. strip HTML with scripts/h2t.py
  3. find the sentence that states a rate limit, a request ceiling, or an
     authentication requirement

The extracted sentence is a quote, kept with the URL and the digest of the page
it came from, so a reader can open the capture and read the sentence in place.
Where no sentence matches, the row says `not-found` rather than inventing a
limit. The report prints how many providers yielded a sentence, and the ones
that did not are named.

Output: data/limits.tsv and evidence/terms/index.tsv
"""
import csv
import hashlib
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (compatible; ar-6f2d90-research-bot; +https://github.com/talaria0101/ar-6f2d90)"
TIMEOUT = 40

# A limit sentence must pair a *number* with a *rate unit*, or state plainly
# that no credential is needed. A page heading such as "Registration and rate
# limits" is not a limit, and neither is "we do not have automatic rate
# limiting in place" -- so the pattern requires an integer and a unit in the
# same clause, and rejects a negation that precedes the number.
NUM = r"\d[\d,]*(?:\.\d+)?"
UNIT = (r"(?:requests?|calls?|queries|items|records|results|DOIs?|pages?|"
        r"papers|works?|hits|searches|tokens)")
PERIOD = (r"(?:per|/|a|an|each|every|in\s+a)\s*"
          r"(?:second|sec|minute|min|hour|day|month|year|10\s*minutes|"
          r"5-minute\s*period|24\s*hours)")
LIMIT_PATTERNS = [
    # The strongest shape: a number, an optional unit noun, then a time period.
    # "60 requests per minute", "7200 requests a day",
    # "2000 requests in a 5-minute period", "1 request per second".
    re.compile(r"[^.;\n]{0,200}?" + NUM + r"\s*(?:" + UNIT + r")?\s*" + PERIOD
               + r"[^.;\n]{0,160}", re.I),
    # A rate word followed by a number and a period in the same clause.
    re.compile(r"[^.;\n]{0,160}?(?:throttled|rate[- ]limited|limited to|maximum of|"
               r"max of|up to|no more than|default rate of)\s+(?:of\s+)?" + NUM
               + r"[^.;\n]{0,60}?" + PERIOD + r"[^.;\n]{0,120}", re.I),
    # An explicit statement that no credential is needed. These carry no number
    # and are reported as an auth fact, not a rate fact.
    re.compile(r"[^.;\n]{0,120}?(?:no (?:API )?key (?:is )?(?:required|needed)|"
               r"without (?:an? )?(?:API )?key|no registration (?:is )?(?:required|needed))"
               r"[^.;\n]{0,160}", re.I),
]
NEGATIONS = ("do not", "don't", "does not", "no automatic", "not subject",
             "no rate limit", "unlimited")


def slug_for(s):
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")[:80]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, path):
    cmd = ["curl", "-sS", "-L", "--max-time", str(TIMEOUT), "--max-filesize", "6000000",
           "-A", UA, "-o", path, "-w", "%{http_code}\t%{time_total}\t%{content_type}", url]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 20)
        parts = res.stdout.strip().split("\t")
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
    except subprocess.TimeoutExpired:
        pass
    return "000", "0", "-"


def to_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        res = subprocess.run([sys.executable, "scripts/h2t.py"], input=raw,
                             capture_output=True, timeout=60)
        return res.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def extract(text):
    """Return the first sentence that states a real limit, one line."""
    flat = re.sub(r"\s+", " ", text)
    best = ""
    for pat in LIMIT_PATTERNS:
        for m in pat.finditer(flat):
            s = m.group(0).strip(" ,;:-|")
            low = s.lower()
            # A negation in the same clause means there is no limit to report.
            if any(n in low for n in NEGATIONS) and not re.search(r"no (?:api )?key", low):
                continue
            if not (20 <= len(s) <= 400):
                continue
            # Prefer a sentence that also names a number over one that does not.
            if re.search(NUM, s):
                return s
            if not best:
                best = s
    return best


def work(args):
    i, row = args
    outdir = "evidence/terms"
    os.makedirs(outdir, exist_ok=True)
    slug = slug_for(row["provider"])
    path = os.path.join(outdir, "%03d_%s.body" % (i, slug))
    code, elapsed, ctype = fetch(row["terms_url"], path)
    if not os.path.exists(path):
        open(path, "wb").close()
    text = to_text(path) if code == "200" else ""
    sentence = extract(text) if text else ""
    index_row = [row["provider"], code, str(os.path.getsize(path)),
                 sha256_file(path), row["terms_url"], path]
    return index_row, {"provider": row["provider"], "code": code,
                       "url": row["terms_url"], "sentence": sentence,
                       "path": path, "bytes": os.path.getsize(path),
                       "sha256": index_row[3]}


def main():
    with open("data/terms_urls.tsv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    jobs = list(enumerate(rows, 1))
    index, limits = [], []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for idx_row, lim in ex.map(work, jobs):
            index.append(idx_row)
            limits.append(lim)
            print("%-28s %s %s" % (lim["provider"], lim["code"],
                                   (lim["sentence"][:90] + "...") if lim["sentence"] else "not-found"))
    with open("evidence/terms/index.tsv", "w", encoding="utf-8") as fh:
        fh.write("provider\tcode\tbytes\tsha256\turl\tpath\n")
        for r in index:
            fh.write("\t".join(r) + "\n")
    with open("data/limits.tsv", "w", encoding="utf-8") as fh:
        fh.write("provider\tcode\tlimit_sentence\tterms_url\tcapture_path\n")
        for r in limits:
            fh.write("\t".join([r["provider"], r["code"],
                                r["sentence"] or "not-found",
                                r["url"], r["path"]]) + "\n")
    found = sum(1 for r in limits if r["sentence"])
    print("\n%d providers, %d with an extracted limit sentence -> data/limits.tsv"
          % (len(limits), found))


if __name__ == "__main__":
    main()
