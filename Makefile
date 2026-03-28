lint:
	flake8 optibroker_common/ tests/

unit-test:
	python -m pytest tests/ -v --cov=optibroker_common --cov-report=term-missing

safety:
	pip-audit
