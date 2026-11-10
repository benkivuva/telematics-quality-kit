.PHONY: verify demo security

verify:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src/telematics
	uv run pytest

demo:
	uv run telematics demo

security:
	gitleaks detect --source . --redact
	semgrep scan --config auto --error
	uv run pip-audit
	trivy fs --severity CRITICAL,HIGH --exit-code 1 .
	docker build --tag telematics-quality-kit:security .
	trivy image --severity CRITICAL,HIGH --exit-code 1 telematics-quality-kit:security
