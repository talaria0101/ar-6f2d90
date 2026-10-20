#!/usr/bin/env python3
"""One implementation of "what fact does this captured body contain".

Used by both scripts/extract_observations.py (which writes the figure into the
report) and scripts/check_reports.py (which verifies the figure against the
bytes). Two independent implementations drifted once already: the extractor
counted one <PubmedArticle> element while the checker fell back to counting 19
lines. A figure that the producer and the verifier compute differently is a
figure nobody can trust, so both now call the same function.

The output is a string of the form `<key>=<value>`:
    total=N      a result-set size the service itself reports
    records=N    the number of records the body contains
    id=X         an identifier, for a single-document endpoint
    image=N      a binary artefact, N bytes
    lines=N      a line-delimited body
    tsv-rows=N   a tab-separated body, excluding its header
    memento=N    a Memento TimeMap, N memento links
    oai-repo=X   an OAI-PMH Identify response naming X
    doc_keys=N   a single JSON document with N top-level keys
"""
import json
import os
import re

TOTAL_PATHS = [
    ("meta", "count"), ("message", "total-results"), ("hits", "total"),
    ("response", "numFound"), ("search", "result_count"), ("stats", "total"),
    ("page_meta", "total_count"), ("esearchresult", "count"),
    ("response", "header", "total", "$"), ("messages", "0", "total"),
    ("_embedded", "searchResult", "page", "totalElements"),
    ("count",), ("total",), ("totalResults",), ("numFound",), ("numberOfResults",),
    ("hitsCount",), ("itemsCount",), ("hitCount",), ("totalCount",),
    ("total_count",), ("number_of_results",), ("totalHits",), ("resultCount",),
]
COUNT_KEYS = {"total", "count", "total_count", "totalcount", "numfound",
              "hitcount", "totalresults", "result_count", "numberofresults",
              "totalelements"}
ARRAY_KEYS = ["results", "items", "records", "docs", "entries", "works", "data",
              "response", "list", "articles", "datasets", "preprints", "papers",
              "feed", "nodes", "occurrence", "studies", "theses", "rows",
              "search", "repositories", "targets", "versions"]
ID_KEYS = ["id", "doi", "identifier", "handle", "uuid", "guid", "accession",
           "orcid", "pmid", "pmcid", "iri", "urlkey", "url", "nctId"]
XML_ROW_TAGS = ("record", "entry", "srw_dc:dc", "doc", "repository", "target",
                "PubmedArticle", "sru:record")


def dig(obj, path):
    cur = obj
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and k.isdigit() and int(k) < len(cur):
            cur = cur[int(k)]
        else:
            return None
    return cur


def deep_count(obj, depth=0):
    if depth > 3:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in COUNT_KEYS and isinstance(v, int):
                return v
            if k.lower() in COUNT_KEYS and isinstance(v, str) and v.isdigit():
                return int(v)
        for v in obj.values():
            got = deep_count(v, depth + 1)
            if got is not None:
                return got
    elif isinstance(obj, list) and obj:
        return deep_count(obj[0], depth + 1)
    return None


def count_rows_json(obj):
    """Return the number of rows a parsed JSON document contains, or None."""
    if isinstance(obj, list):
        # A CDX response is a list of lists whose first element is the column
        # header; counting it would overstate by one.
        if obj and isinstance(obj[0], list) and all(isinstance(c, str) for c in obj[0]):
            return len(obj) - 1
        return len(obj)
    if not isinstance(obj, dict):
        return None
    for k in ARRAY_KEYS:
        v = obj.get(k)
        if isinstance(v, list):
            return len(v)
        if isinstance(v, dict):
            for kk in ("docs", "items", "results", "records", "bindings", "hits"):
                if isinstance(v.get(kk), list):
                    return len(v[kk])
    b = dig(obj, ("results", "bindings"))
    if isinstance(b, list):
        return len(b)
    return None


def count_rows_xml(text):
    n = 0
    for tag in XML_ROW_TAGS:
        n += len(re.findall(r"<%s[ >]" % re.escape(tag), text))
    return n


def observe(body, path):
    """Return the `<key>=<value>` fact for a captured body."""
    s = body.strip()
    with open(path, "rb") as raw:
        head = raw.read(4)

    try:
        obj = json.loads(s)
    except Exception:
        obj = None

    if obj is not None:
        for p in TOTAL_PATHS:
            v = dig(obj, p)
            if isinstance(v, int):
                return "total=%d" % v
            if isinstance(v, str) and v.isdigit():
                return "total=%s" % v
        n = count_rows_json(obj)
        if n is not None:
            return "records=%d" % n
        got = deep_count(obj)
        if got is not None:
            return "total=%d" % got
        if isinstance(obj, dict):
            for k in ID_KEYS:
                if k in obj and isinstance(obj[k], (str, int)):
                    return "id=%s" % str(obj[k])[:60]
            return "doc_keys=%d" % len(obj)
        return "records=0"

    # Non-JSON, in an order that keeps each special shape out of the generic
    # branches. An OAI Identify and a TimeMap carry no count at all.
    if "OAI-PMH" in s[:600]:
        m = re.search(r"<repositoryName>([^<]{0,80})<", s)
        return "oai-repo=%s" % (m.group(1) if m else "identify")
    if 'rel="original"' in s:
        return "memento=%d" % len(re.findall(r'rel="memento"', s))
    if head[:3] == b"\xff\xd8\xff" or head[:4] == b"\x89PNG" or head[:4] == b"%PDF":
        return "image=%d" % os.path.getsize(path)
    if s.startswith("<") or "<?xml" in s[:100]:
        for tag in ("totalResults", "opensearch:totalResults", "numberOfRecords",
                    "srw:numberOfRecords", "totalHits", "totalNumberOfResults"):
            m = re.search(r"<%s[^>]*>(\d+)<" % re.escape(tag), s)
            if m:
                return "total=%s" % m.group(1)
        m = re.search(r'num-found="(\d+)"', s)
        if m:
            return "total=%s" % m.group(1)
        n = count_rows_xml(s)
        if n:
            return "records=%d" % n
        return "lines=%d" % len([ln for ln in s.splitlines() if ln.strip()])
    if s.splitlines() and s.splitlines()[0].strip().startswith("{"):
        return "lines=%d" % len([ln for ln in s.splitlines() if ln.strip()])
    if s.splitlines() and "\t" in s.splitlines()[0]:
        return "tsv-rows=%d" % max(0, len([ln for ln in s.splitlines() if ln.strip()]) - 1)
    return "lines=%d" % len([ln for ln in s.splitlines() if ln.strip()])
