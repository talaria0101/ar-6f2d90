#!/usr/bin/env python3
"""Join the service map to the probe evidence and emit the provider table.

Usage: python3 scripts/build_table.py

Reads:
  data/service_map.tsv       one row per endpoint, with the probe slug that
                             demonstrates it
  evidence/verdicts.tsv      per-probe verdict, reason, code, bytes, sha256
  evidence/observations.tsv  one extracted fact per payload probe

Writes data/providers.tsv: one row per endpoint, carrying the artefact that
proves the claim. An endpoint whose probe is not a payload is excluded and
printed by name with its verdict; it is never silently dropped and never
silently included.

Columns:
  provider service category kind auth code bytes observed host
  probe_slug probe_url sha256 evidence_path docs home
"""
import csv
import os
import sys


def load_tsv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main():
    services = load_tsv("data/service_map.tsv")
    verdicts = {}
    for row in load_tsv("evidence/verdicts.tsv"):
        # First capture of a slug wins. Later captures of the same URL stay in
        # the evidence index; the report notes where they disagree.
        verdicts.setdefault(row["slug"], row)
    observations = {}
    for row in load_tsv("evidence/observations.tsv"):
        observations.setdefault(row["slug"], row)

    fields = ["provider", "service", "category", "kind", "auth", "code", "bytes",
              "observed", "host", "probe_slug", "probe_url", "sha256",
              "evidence_path", "docs", "home"]

    out_rows = []
    excluded = []
    for s in services:
        slug = s["probe_slug"]
        v = verdicts.get(slug)
        if v is None:
            excluded.append((s["service"], slug, "no-probe-row", ""))
            continue
        if v["verdict"] != "payload":
            excluded.append((s["service"], slug, v["verdict"], v["reason"]))
            continue
        obs = observations.get(slug, {})
        out_rows.append({
            "provider": s["provider"],
            "service": s["service"],
            "category": s["category"],
            "kind": s["kind"],
            "auth": s["auth"],
            "code": v["code"],
            "bytes": v["bytes"],
            "observed": obs.get("observed", "unparsed"),
            "host": s.get("host", ""),
            "probe_slug": slug,
            "probe_url": obs.get("url", s.get("probe_url", "")),
            "sha256": v["sha256"],
            "evidence_path": v["path"],
            "docs": s["docs"],
            "home": s["home"],
        })

    with open("data/providers.tsv", "w", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)

    print("%d endpoints in map, %d in table, %d excluded, %d providers"
          % (len(services), len(out_rows), len(excluded),
             len({r["provider"] for r in out_rows})))
    for name, slug, verdict, reason in excluded:
        print("  EXCLUDED %-32s slug=%-18s %s %s" % (name, slug, verdict, reason))


if __name__ == "__main__":
    main()
