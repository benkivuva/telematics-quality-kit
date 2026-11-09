.PHONY: verify demo security

verify:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src/telematics
	uv run pytest

demo:
	uv run telematics demo

security:
	uv run pip-audit
