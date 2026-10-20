# Methodology

This file explains how every figure in `report/01` to `report/03` was produced,
how to check one against a captured artefact, and what this pass did not cover.

## What this repository is

An inventory of academic and archival services that publish a programmatic API,
each one demonstrated by a live unauthenticated request made from this sandbox
on 2026-10-20. The question it answers is narrow: which services answer a query
over HTTP with no account, and what does the answer look like.

It is not a ranking, a benchmark, or a survey of data quality. No two services
here were asked the same question in the same way, because they do not share a
query language. The `observed` column records what each one returned to the
probe in `probe_url`, and nothing more.

## The two reference repositories, and what changed

This pass adopts the method of `Nemo-010/w-search-3f9a2c` and
`talaria0101/w-search-7b668b35`: a candidate list, a captured page per claim, a
per-row evidence index with SHA-256, a generated report, and a checker that
refuses a row whose source is not in the index.

Two things are different here, and both are deliberate:

1. **This pass makes live API calls.** Both reference repositories state
   plainly that they did not: "No live API calls to most providers. Every
   figure is from a captured public page." For a web-scraping inventory that
   limitation is acceptable, because the product is a fetched page. For an
   API inventory it is not: an endpoint that documents a search API and refuses
   every anonymous request is not a usable service, and a documentation page
   cannot tell you which one it is. Every row in `report/01` is backed by a
   captured HTTP response to a real query.

2. **The checker recomputes the reported figure.** The reference checker
   validates that a source URL is in the evidence index and returned 200. That
   proves the page was fetched. It does not prove the number beside it came
   from that page. Here `scripts/check_reports.py` re-derives every `observed`
   value from the captured bytes with the same function the report used
   (`scripts/observe_lib.py`), so a hand-edited figure fails.

The `llms.txt` test is kept from the reference pass, including its rejection
rules, and extended with a platform-host test after it produced a false
positive here (see "What the gates caught" below).

## Pipeline

```
data/candidates*.tsv      candidate list, one row per URL to probe
        |
        v
scripts/probe_candidates.py   fetch each URL, write evidence/probe<n>/
        |
        v
scripts/classify_probes.py    read each body, assign a verdict and a reason
        |
        v
scripts/extract_observations.py   one fact per payload, via observe_lib
        |
        v
data/service_map.tsv      one row per endpoint, naming its probe
        |
        v
scripts/build_table.py    join map to evidence -> data/providers.tsv
        |
        v
scripts/build_report.py   -> report/01-providers.md
scripts/build_exclusions.py -> report/02-exclusions.md
```

Every step is re-runnable and idempotent. Nothing in `report/` is edited by
hand.

## The probe

Each candidate URL is requested once with:

- no API key, no token, no account;
- a `User-Agent` that names this project and links to it, so a host that blocks
  it blocks it visibly rather than silently;
- a 40-second timeout and a response size cap, so a runaway endpoint cannot
  fill the disk.

The query in each URL is `test` or a fixed identifier, chosen so the request is
cheap and the response small. The exact URL is in `probe_url` for every row.

A probe result is not a statement about a service's capacity. It is one request
from one IP at one moment.

## Verdicts

`scripts/classify_probes.py` reads the body, not just the status code, and
assigns one of:

| verdict | meaning |
|---|---|
| `payload` | an HTTP 2xx whose body carries content: JSON, XML, NDJSON, link-format, text or a binary artefact. Only this verdict enters `report/01`. |
| `auth` | 401/403, or a body that names a missing key, token or login. |
| `challenge` | a bot interstitial (Cloudflare, Anubis, bunny-shield, reCAPTCHA). |
| `throttled` | 429, or a body that says the caller exceeded a rate. |
| `empty` | zero bytes, or 202 with no body. |
| `banner` | an API root that returns a version string rather than a result. |
| `error` | 404/410/5xx, or an error document. |
| `unreachable` | transport failure: DNS, TLS, proxy, timeout. |

Reading the body is necessary in both directions. Cloudflare and Anubis serve a
200 interstitial, so a status-code-only rule would list them as working.
DPLA, Lens, ADS, Trove and the DDB serve a 401/403 JSON refusal, so a
status-code-only rule would count them as blocked when they are merely keyed.
OpenAlex serves a 200 payload whose `meta.notice` mentions an API key, so a
naive keyword rule would count it as blocked when it is working.

The rule that resolves these, implemented in `scripts/classify_probes.py`:

- a bot-wall marker anywhere in the first 4 kB is a `challenge`, whatever the
  status code;
- a JSON body under 300 bytes that names a rate or a key is `throttled` or
  `auth`;
- otherwise a 2xx is a `payload` and a non-2xx is classified by its class.

The 300-byte threshold is what separates a refusal from a result. The longest
refusal body in this pass is 318 bytes (OpenAlex's response to a bad `api_key`);
19 payloads are under 300 bytes, the smallest 10 bytes (`{"ping":1}` from
Ensembl). No payload under 300 bytes contains a refusal marker, so the two
classes do not overlap in this evidence set. A larger body that mentions "API
key" in a notice field, which OpenAlex's 18 kB response does, stays a payload.

## The `observed` figure

One fact per row, extracted mechanically from the captured body:

| shape | meaning |
|---|---|
| `total=N` | a result-set size the service reports |
| `records=N` | the number of records the body contains |
| `id=X` | an identifier, for a single-document endpoint |
| `image=N` | a binary artefact of N bytes |
| `lines=N` / `tsv-rows=N` | a line-delimited or tab-separated body |
| `memento=N` | N memento links in a TimeMap |
| `oai-repo=X` | an OAI-PMH Identify response naming X |
| `doc_keys=N` | a single JSON document with N top-level keys |

A `total=N` is what the service said its corpus contains for that query. It is
not a claim that the corpus is that size for a different query, and it is not a
quality measure. `total=187797949` for Crossref is the number of DOIs matching
the probe's filter at that moment.

## What the gates caught

These are recorded because each one was a defect in this pass's own work, found
by its own checks, and each is the reason a rule exists:

- **`llms.txt` false positive.** `https://github.com/llms.txt` is served for any
  repository path and describes GitHub, not the service whose docs live there.
  It passed every check the reference method uses (200, markdown, a heading, a
  link index). iDigBio was recorded as having an `llms.txt` on that basis. The
  fix is a platform-host rejection list, and the count of verified `llms.txt`
  files fell from 5 to 1.
- **Extractor and checker disagreed.** The extractor counted one
  `<PubmedArticle>` element; a separately written checker counted 19 lines.
  Both were "right" under their own rule, which meant neither could detect a
  wrong figure. The fix is one shared implementation
  (`scripts/observe_lib.py`) called by both.
- **A wrong query, reported as a service fact.** `cat:physics` is a category
  group in arXiv, not a leaf category, and returns `totalResults=0`. The row
  was initially reported as an arXiv result. It was replaced with `cat:hep-th`,
  which returns 186757.
- **A figure attributed to the wrong file.** Three curated limit quotes cited
  `045_`, `050_` and `060_` when the captures were `041_`, `049_` and `062_`.
  `scripts/check_limits.py` refused all three.
- **A mislabelled auth column.** DigitalNZ and Mendeley Data were recorded as
  `key-required` while their probes had returned payloads anonymously. Corrected
  against the captures.

Each gate was tested by planting the defect it exists to catch and confirming
it exits non-zero. `scripts/check_reports.py` was given a fabricated `total`,
a tampered SHA-256, a wrong byte count, and a slug whose verdict is `challenge`;
it refused all four and passed the restored tree.

## How to verify one row

```sh
# 1. Recompute every figure from the captured bytes.
python3 scripts/check_reports.py

# 2. Verify the curated limit quotes.
python3 scripts/check_limits.py

# 3. Read the captured body behind one row.
python3 - <<'EOF'
import csv
for r in csv.DictReader(open('data/providers.tsv'), delimiter='\t'):
    if r['service'] == 'OpenAlex':
        print(r['probe_url']); print(r['evidence_path']); print(r['observed'])
EOF
python3 scripts/h2t.py < <path from above> | head -40
```

`check_reports.py` exits 1 with one line per failure: a figure that does not
recompute, a digest that does not match, a size that does not match, a probe
that did not return a payload, a duplicate service, an out-of-set category, or
a service present in one file and not the other.

## Coverage

| measure | value |
|---|---|
| candidate URLs probed | 347 |
| probes that returned a payload | 178 |
| probes blocked by a bot wall | 34 |
| probes refused for want of a key | 20 |
| probes that failed to connect | 27 |
| endpoints in the table | 137 |
| distinct providers | 68 |
| distinct hosts | 75 |
| docs pages captured | 123 |
| terms pages captured | 68 |
| documented limits with a verified quote | 17 |
| hosts publishing a verified `llms.txt` | 1 of 74 probed |

The candidate list grew in four waves. The first wave was 84 URLs written from
prior knowledge of the field; the second and third were corrections and
extensions after the first wave showed which hosts challenge, which need keys,
and which paths were wrong; the fourth targeted services the earlier waves
missed. Wave two exists because several "failures" in wave one were wrong
endpoints rather than absent services, and correcting them turned 403s into
payloads.

## What this does not cover

- **No keyed probes.** No API key was used anywhere. Every allowance reported
  is the anonymous one. Services that require a key are in
  `report/02-exclusions.md` under `auth`, with the refusal body captured. This
  is the largest gap: it is why a service like DPLA or ADS is absent from the
  table despite having a documented free tier.
- **No rate-limit testing.** No limit was exercised by exceeding it. The quotes
  in `report/03-limits.md` are what the pages say, not what the servers
  enforce.
- **One query per endpoint.** A service that answers `test` but fails a
  structured query, a paginated query, or a large result set is recorded as
  working. Pagination, cursors and error handling were not exercised except
  where the probe URL happened to include them.
- **No data-quality assessment.** Whether a corpus is complete, current or
  correct is not measured. `total=N` says how many records matched, not whether
  they are good.
- **No terms-of-service analysis.** Nothing here says whether a given use of a
  service is permitted by its terms. That question needs a lawyer, not a probe.
- **Bot-walled services are unresolved, not absent.** 34 probes hit a challenge
  page. Those services may well have working public APIs; this sandbox could
  not reach them. They are listed with their captures in
  `report/02-exclusions.md`.
- **The `observed` figure is a sample.** It is one request on one day. A
  service whose corpus changes daily will report a different number tomorrow.
- **No `llms.txt` coverage worth reporting.** 1 host of 74 publishes a verified
  markdown index at that path (`support.datacite.org`). Six DataCite endpoints
  share that one file, which is why the count is per host and not per endpoint.
  This is a finding about the convention's uptake among academic and archival
  services, not a gap in the probe: every host was tried at both its apex and
  its documentation host.

## Re-running

```sh
python3 scripts/classify_probes.py        # re-derive verdicts from the bodies
python3 scripts/extract_observations.py   # re-derive the observed figures
python3 scripts/build_table.py            # rebuild data/providers.tsv
python3 scripts/build_report.py           # rebuild report/01
python3 scripts/build_exclusions.py       # rebuild report/02
python3 scripts/build_limits_report.py    # rebuild report/03
python3 scripts/check_reports.py          # verify every figure
python3 scripts/check_limits.py           # verify every limit quote
```

To re-capture from the network, re-run the probe and capture scripts first.
That rewrites the evidence tree and the digests, and every report must then be
rebuilt before the checkers will pass.
