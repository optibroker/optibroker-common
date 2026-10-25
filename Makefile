lint:
	flake8 optibroker_common/ tests/

unit-test:
	python -m pytest tests/ -v --cov=optibroker_common --cov-report=term-missing

safety:
	pip-audit

PYTHON ?= python3

# Fails if any requirement is behind its latest release. Runs on every PR.
requirements-check:
	$(PYTHON) scripts/check-requirements.py

# Rewrites out-of-date requirements to their latest release.
requirements-update:
	$(PYTHON) scripts/check-requirements.py --update
