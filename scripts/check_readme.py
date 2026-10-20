#!/usr/bin/env python3
"""Verify the headline figures in README.md against the data files.

Usage: python3 scripts/check_readme.py

README.md states counts: providers, endpoints, probes, payloads, challenges,
keyed refusals, hosts publishing llms.txt. Each of those is derivable from the
evidence tree, and each has drifted once already (a hand-written 76 became 75
when the count moved from endpoints to hosts). This script recomputes them and
fails on any mismatch, so the summary cannot disagree with the data.

A README claim that is not in the checked set is not verified by this script;
the report is where the detail lives.
"""
import csv
import json
import os
import re
import sys
from urllib.parse import urlparse


def count_rows(path):
    with open(path, encoding="utf-8") as fh:
        return sum(1 for _ in fh) - 1


def main():
    providers = list(csv.DictReader(open("data/providers.tsv"), delimiter="\t"))
    verdicts = list(csv.DictReader(open("evidence/verdicts.tsv"), delimiter="\t"))
    llms = json.load(open("data/llms.json"))

    actual = {
        "providers": len({r["provider"] for r in providers}),
        "endpoints": len(providers),
        "probes": len(verdicts),
        "payloads": sum(1 for r in verdicts if r["verdict"] == "payload"),
        "challenges": sum(1 for r in verdicts if r["verdict"] == "challenge"),
        "auth": sum(1 for r in verdicts if r["verdict"] == "auth"),
        "llms_hosts_ok": len({urlparse(l["url"]).hostname for l in llms if l["ok"]}),
        "llms_hosts_probed": len({urlparse(l["url"]).hostname for l in llms}),
        "limits": count_rows("data/limits_curated.tsv"),
        "hosts": len({r["host"] for r in providers}),
    }

    text = open("README.md", encoding="utf-8").read()

    # Each pattern names the README line it validates.
    checks = [
        (r"\| providers \| (\d+) \|", "providers"),
        (r"\| endpoints that answered anonymously \| (\d+) \|", "endpoints"),
        (r"\| candidate URLs probed \| (\d+) \|", "probes"),
        (r"\| payloads returned \| (\d+) \|", "payloads"),
        (r"\| probes blocked by a bot wall \| (\d+) \|", "challenges"),
        (r"\| probes refused for want of a key \| (\d+) \|", "auth"),
        (r"\| hosts publishing a verified `llms\.txt` \| (\d+) of (\d+) \|", "llms"),
        (r"\| `report/03-limits\.md` \| (\d+) documented rate limits", "limits"),
    ]

    errors = []
    for pattern, key in checks:
        m = re.search(pattern, text)
        if not m:
            errors.append("README: no line matching %r for %s" % (pattern, key))
            continue
        if key == "llms":
            got_ok, got_probed = int(m.group(1)), int(m.group(2))
            if got_ok != actual["llms_hosts_ok"]:
                errors.append("README: llms verified %d, data says %d"
                              % (got_ok, actual["llms_hosts_ok"]))
            if got_probed != actual["llms_hosts_probed"]:
                errors.append("README: llms probed %d, data says %d"
                              % (got_probed, actual["llms_hosts_probed"]))
        else:
            got = int(m.group(1))
            if got != actual[key]:
                errors.append("README: %s %d, data says %d" % (key, got, actual[key]))

    # The methodology coverage table must agree too.
    meth = open("report/00-methodology.md", encoding="utf-8").read()
    meth_checks = [
        (r"\| candidate URLs probed \| (\d+) \|", "probes"),
        (r"\| probes that returned a payload \| (\d+) \|", "payloads"),
        (r"\| endpoints in the table \| (\d+) \|", "endpoints"),
        (r"\| distinct providers \| (\d+) \|", "providers"),
        (r"\| probes blocked by a bot wall \| (\d+) \|", "challenges"),
        (r"\| probes refused for want of a key \| (\d+) \|", "auth"),
        (r"\| documented limits with a verified quote \| (\d+) \|", "limits"),
        (r"\| distinct hosts \| (\d+) \|", "hosts"),
        (r"\| hosts publishing a verified `llms\.txt` \| (\d+) of (\d+) probed \|", "llms"),
    ]
    for pattern, key in meth_checks:
        m = re.search(pattern, meth)
        if not m:
            errors.append("methodology: no line matching %r for %s" % (pattern, key))
            continue
        if key == "llms":
            if int(m.group(1)) != actual["llms_hosts_ok"] or int(m.group(2)) != actual["llms_hosts_probed"]:
                errors.append("methodology: llms %s of %s, data says %d of %d"
                              % (m.group(1), m.group(2), actual["llms_hosts_ok"],
                                 actual["llms_hosts_probed"]))
        else:
            if int(m.group(1)) != actual[key]:
                errors.append("methodology: %s %s, data says %d"
                              % (key, m.group(1), actual[key]))

    if errors:
        print("FAIL (%d problems)" % len(errors))
        for e in errors:
            print("  - " + e)
        return 1
    print("PASS: README and methodology headline figures match the data "
          "(%d providers, %d endpoints, %d probes, %d payloads, %d llms hosts)"
          % (actual["providers"], actual["endpoints"], actual["probes"],
             actual["payloads"], actual["llms_hosts_ok"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
