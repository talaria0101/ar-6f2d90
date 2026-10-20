# Academic and archival services with a public API

An inventory of 68 providers and 123 endpoints across scholarly indexes,
repositories, web archives, library catalogues, museum collections and research
data services, each demonstrated by a live unauthenticated HTTP request made
from a sandbox on 2026-10-20.

Every figure in the reports is recomputed from the captured response bytes by
`scripts/check_reports.py`. Nothing in `report/` is written by hand.

## What is here

| path | contents |
|---|---|
| `report/00-methodology.md` | how every figure was produced, the gates that caught this pass's own errors, and what was not covered |
| `report/01-providers.md` | 137 endpoints across 68 providers, one row each, with the observed fact and the captured body |
| `report/02-exclusions.md` | every probed URL that did not produce a row, grouped by why |
| `report/03-limits.md` | 17 documented rate limits, each with a quote verified against its capture |
| `data/providers.tsv` | the table, machine readable |
| `data/service_map.tsv` | endpoint to probe mapping, including the provider rollup |
| `data/limits.tsv`, `data/limits_curated.tsv` | extracted and hand-verified limit sentences |
| `data/candidates*.tsv` | the 347 candidate URLs that were probed |
| `evidence/` | the captured bodies, with an index of URL, status, bytes and SHA-256 per file |

## The headline numbers

| measure | value |
|---|---|
| providers | 68 |
| endpoints that answered anonymously | 137 |
| candidate URLs probed | 347 |
| payloads returned | 178 |
| probes blocked by a bot wall | 34 |
| probes refused for want of a key | 20 |
| hosts publishing a verified `llms.txt` | 1 of 74 |

## What makes this different from a page-scraping inventory

Two things, both explained in the methodology:

1. **The probes are live.** A documented search API that refuses every
   anonymous request is not a usable service, and only a request can tell you
   which one it is. Each row carries the query that produced it.
2. **The checker recomputes the figure.** A row is not valid because its source
   URL returned 200. It is valid because `check_reports.py` re-reads the
   captured bytes and derives the same number the report printed.

## Verify

```sh
make check      # recompute every figure, verify every digest and limit quote
```

or directly:

```sh
python3 scripts/check_reports.py
python3 scripts/check_limits.py
```

Both exit 0 on success and print one line per failure otherwise.

## Rebuild

```sh
make reports    # regenerate report/01, report/02, report/03 from data/
make check
```

## Limits of this inventory

Stated in full in `report/00-methodology.md`. The short version:

- No API key was used, so every allowance is the anonymous one. Services that
  require a key are excluded and named, not silently dropped.
- No rate limit was exercised by exceeding it. The quotes are what the pages
  say, not what the servers enforce.
- One query per endpoint. Pagination, cursors and error handling were not
  exercised except where the probe URL included them.
- No data-quality assessment and no terms-of-service analysis.
- 34 services answered with a bot challenge. They are unresolved from this
  sandbox, not shown to be without an API.

## Licence

0BSD. See `LICENSE`.
