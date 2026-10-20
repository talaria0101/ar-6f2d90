#!/usr/bin/env python3
"""Classify every probe body as payload, throttled, auth, error, empty or unreachable.

Usage: python3 scripts/classify_probes.py

Reads evidence/probe*/index.tsv, opens each body, and decides from the body
first and the status code second:

  payload     an HTTP 2xx whose body carries content: JSON, XML, NDJSON,
              link-format, text or a binary artefact. The only verdict counted
              as a working anonymous endpoint.
  banner      an HTTP 2xx whose body is a service banner with no result in it
              (Scite returns {"message":"Scite API","version":"..."}).
  throttled   429, or a body that says the caller exceeded a rate.
  auth        401/403, or a body that names a missing key, token or login.
  error       404/410/5xx, or an error document with no content.
  empty       zero bytes, or 202 with no body.
  challenge   a bot interstitial served instead of the API.
  unreachable transport failure: DNS, TLS, proxy, timeout.

Why the body is read: the status code alone misclassifies in both directions
here. Cloudflare and Anubis serve a 200 interstitial; DPLA, Lens, ADS and
Trove serve a 401/403 JSON refusal; OpenAlex serves a 200 payload whose
meta.notice mentions an API key.

The rule, in order:
  1. a bot-wall marker anywhere in the first 4 kB is a challenge;
  2. in JSON, a *short* body (<1500 bytes of canonical JSON) that names a
     rate or a key is throttled/auth. The length test is what keeps OpenAlex
     (18 kB payload with "API key" in meta.notice) out of the auth bucket;
  3. otherwise a 2xx is a payload and a non-2xx is classified by its class.

Every row records `reason`, a short tag, so a verdict can be audited without
re-reading the body.
"""
import csv
import json
import os
import sys

CHALLENGE_MARKS = [
    "just a moment", "making sure you're not a bot", "challenge verification required",
    "bunny-shield", "session verification", "cf-chl", "__cf_chl",
    "access denied", "attention required", "establishing a secure connection",
    "pardon our interruption", "enable javascript and cookies",
]
AUTH_MARKS = [
    "api key", "apikey", "api_key", "authorization", "invalid_api_key",
    "not authorized", "unauthorized", "please login", "no api key found",
    "security level does not allow", "missing/incorrect authorization",
    "you must supply an api key", "please login before continuing",
    "missing authorization", "notauthorizedexception", "key is required",
    "requires an api key",
]
THROTTLE_MARKS = ["exceeds allowed rate", "rate limit", "too many requests",
                  "quota exceeded", "slow down", "try again later"]
BANNER_KEYS = {"message", "version", "status", "code"}


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def try_json(s):
    try:
        return json.loads(s)
    except Exception:
        return None


def has_any(text, marks):
    return any(m in text for m in marks)


def judge(body, code, ctype):
    """Return (verdict, reason)."""
    if code == "000":
        return "unreachable", "transport"
    s = body.strip()
    if not s:
        return "empty", "no-body"
    low = s[:4000].lower()

    # 1. Bot interstitials win over everything: a 200 challenge is not a result.
    if has_any(low, CHALLENGE_MARKS):
        return "challenge", "bot-wall"

    # 2. JSON.
    obj = try_json(s)
    if obj is not None:
        keys = set(obj) if isinstance(obj, dict) else set()
        blob = json.dumps(obj, separators=(",", ":"))[:3000]
        # A refusal is short. Europeana's 982-byte result page echoes
        # "apikey":"api2demo" and is a payload; DPLA's 132-byte
        # {"error":"invalid_api_key"} is a refusal. 300 bytes separates them.
        small = len(s) < 300
        if small and has_any(blob.lower(), THROTTLE_MARKS):
            return "throttled", "rate-message"
        if small and has_any(blob.lower(), AUTH_MARKS):
            return "auth", "key-required"
        if isinstance(obj, dict) and keys and keys <= BANNER_KEYS:
            return "banner", "no-result"
        if code.startswith("2"):
            return "payload", "json"
        if code in {"401", "403"}:
            return "auth", "http-" + code
        if code == "429":
            return "throttled", "http-429"
        return "error", "http-" + code

    # 3. NDJSON.
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines and all(ln.startswith("{") for ln in lines[:5]) and try_json(lines[0]) is not None:
        return ("payload", "ndjson") if code.startswith("2") else ("error", "http-" + code)

    # 4. XML.
    if s.startswith("<?xml") or s.startswith("<feed") or s.startswith("<records") \
            or s.startswith("<OAI-PMH") or s.startswith("<sru") or s.startswith("<record"):
        if "<error" in low[:800]:
            if has_any(low, THROTTLE_MARKS):
                return "throttled", "xml-rate"
            return ("auth", "xml-forbidden") if code in {"401", "403"} else ("error", "xml-error")
        return ("payload", "xml") if code.startswith("2") else ("error", "http-" + code)

    # 5. Memento link-format.
    if 'rel="original"' in s or 'rel="timegate"' in s:
        return ("payload", "link-format") if code.startswith("2") else ("error", "http-" + code)

    # 6. Binary artefacts (images, PDFs, archives).
    if code.startswith("2") and ctype and not ctype.startswith(
            ("text/", "application/json", "application/xml", "application/atom",
             "application/vnd.api", "application/sparql")):
        return "payload", "binary"

    # 7. HTML and plain text.
    if s.startswith("<") and ("<html" in low or "<!doctype html" in low):
        if len(s) < 20000 and has_any(low, AUTH_MARKS):
            return "auth", "html-login-wall"
        return ("error", "http-" + code) if (code in {"404", "410"} or code.startswith("5")) \
            else ("html", "html-only")
    if has_any(low, AUTH_MARKS):
        return "auth", "key-required"
    if has_any(low, THROTTLE_MARKS):
        return "throttled", "rate-message"
    if code in {"401", "403"}:
        return "auth", "http-" + code
    if code == "429":
        return "throttled", "http-429"
    if code in {"404", "410"} or code.startswith("5"):
        return "error", "http-" + code
    if code.startswith("2"):
        return "payload", "text"
    return "error", "http-" + code


def main():
    rows = []
    skipped = 0
    for d in sorted(os.listdir("evidence")):
        # Only probe batches. evidence/docs holds a different schema
        # (service-keyed) and is classified by its own script.
        if not d.startswith("probe"):
            continue
        idx = os.path.join("evidence", d, "index.tsv")
        if not os.path.exists(idx):
            continue
        with open(idx, encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                body = load(row["path"])
                if body is None:
                    skipped += 1
                    continue
                ctype = row.get("content_type", "") or ""
                row["verdict"], row["reason"] = judge(body, row["code"], ctype)
                row["batch"] = d
                rows.append(row)
    out = "evidence/verdicts.tsv"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("slug\tcode\tbytes\tverdict\treason\tbatch\tsha256\turl\tpath\n")
        for r in rows:
            fh.write("\t".join([r["slug"], r["code"], r["bytes"], r["verdict"],
                                r["reason"], r["batch"], r["sha256"], r["url"],
                                r["path"]]) + "\n")
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("%d probes classified -> %s" % (len(rows), out))
    if skipped:
        print("  %d index rows skipped: captured body no longer on disk" % skipped)
    for k in sorted(counts):
        print("  %-11s %d" % (k, counts[k]))
    payloads = {r["slug"] for r in rows if r["verdict"] == "payload"}
    print("  distinct slugs with a payload: %d" % len(payloads))


if __name__ == "__main__":
    main()
