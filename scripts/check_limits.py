#!/usr/bin/env python3
"""Verify the curated limit quotes against the captures they cite.

Usage: python3 scripts/check_limits.py

data/limits_curated.tsv holds the limit sentences a human read out of the
captured terms pages, with the exact quote. This script proves each quote is
present in the capture it names, after the same HTML-to-text step the capture
used. A quote that is not in the file is a fabricated citation and fails here.

The regex extractor in scripts/capture_terms.py finds only the shapes it was
told to find. The curated file covers the pages where the limit sits in a
table or in a sentence the pattern does not reach. Both end up in the report,
and both are checked.
"""
import csv
import os
import re
import subprocess
import sys


def to_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    res = subprocess.run([sys.executable, "scripts/h2t.py"], input=raw,
                         capture_output=True, timeout=60)
    return res.stdout.decode("utf-8", "replace")


def main():
    errors = []
    rows = []
    with open("data/limits_curated.tsv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            path = row["capture_path"]
            if not os.path.exists(path):
                errors.append("%s: capture missing %s" % (row["provider"], path))
                continue
            text = re.sub(r"\s+", " ", to_text(path))
            quote = re.sub(r"\s+", " ", row["limit_quote"]).strip()
            if quote not in text:
                errors.append("%s: quote not present in %s" % (row["provider"], path))
                continue
            rows.append(row)

    if errors:
        print("FAIL (%d problems)" % len(errors))
        for e in errors:
            print("  - " + e)
        return 1
    print("PASS: %d curated limit quotes are present in their cited captures" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
