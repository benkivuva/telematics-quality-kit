.PHONY: verify demo security coverage

verify:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src/telematics
	uv run pytest

coverage:
	uv run pytest --cov=telematics.codecs --cov=telematics.quality \
		--cov=telematics.service --cov=telematics.mcp --cov=telematics.eval \
		--cov-report=term-missing --cov-fail-under=85
	for package in codecs quality service mcp; do \
		uv run coverage report --include="*/telematics/$$package/*" --fail-under=85; \
	done

demo:
	uv run telematics demo

security:
	gitleaks detect --source . --redact
	semgrep scan --config auto --error
	uv run pip-audit
	trivy fs --severity CRITICAL,HIGH --exit-code 1 .
	docker build --tag telematics-quality-kit:security .
	trivy image --ignore-unfixed --severity CRITICAL,HIGH --exit-code 1 telematics-quality-kit:security
