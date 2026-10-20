.PHONY: check reports exclusions limits all clean

# Rebuild every generated report from the captured evidence.
reports:
	python3 scripts/classify_probes.py
	python3 scripts/extract_observations.py
	python3 scripts/build_table.py
	python3 scripts/build_report.py
	python3 scripts/build_exclusions.py
	python3 scripts/build_limits_report.py

# Verify every figure and every quote against the captured bytes.
check:
	python3 scripts/check_reports.py
	python3 scripts/check_limits.py
	python3 scripts/check_readme.py

all: reports check

# Re-probe the network. This rewrites evidence/ and every digest, so the
# reports must be rebuilt afterwards before `make check` will pass.
probe:
	python3 scripts/probe_candidates.py data/candidates.tsv
	python3 scripts/probe_candidates.py data/candidates2.tsv
	python3 scripts/probe_candidates.py data/candidates3.tsv
	python3 scripts/probe_candidates.py data/candidates4.tsv

docs:
	python3 scripts/capture_docs.py
	python3 scripts/capture_terms.py
