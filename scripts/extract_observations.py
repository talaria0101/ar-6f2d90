#!/usr/bin/env python3
"""Extract one observed fact from each probe payload.

Usage: python3 scripts/extract_observations.py

For every row in evidence/verdicts.tsv whose verdict is `payload`, read the
captured body and record the strongest single fact it contains, as
`<key>=<value>` (see scripts/observe_lib.py for the shapes).

The point is to stop at a status code. A 200 with a valid empty envelope is
not evidence that an endpoint answers a query; a 200 with total=46542 is.

Output: evidence/observations.tsv
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from observe_lib import observe  # noqa: E402


def main():
    rows = []
    with open("evidence/verdicts.tsv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["verdict"] != "payload":
                continue
            with open(row["path"], encoding="utf-8", errors="replace") as bf:
                body = bf.read()
            row["observed"] = observe(body, row["path"])
            rows.append(row)
    out = "evidence/observations.tsv"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("slug\tcode\tbytes\tobserved\turl\tpath\n")
        for r in rows:
            fh.write("\t".join([r["slug"], r["code"], r["bytes"], r["observed"],
                                r["url"], r["path"]]) + "\n")
    print("%d payload rows -> %s" % (len(rows), out))
    bad = [r["slug"] for r in rows if r["observed"].endswith("=unparsed")]
    if bad:
        print("  unparsed: %s" % " ".join(sorted(bad)))


if __name__ == "__main__":
    main()
