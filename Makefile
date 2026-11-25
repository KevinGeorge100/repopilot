.PHONY: install lint test web-check check dev
install:
	uv sync
	cd web && npm ci
lint:
	uv run ruff check .
test:
	uv run pytest -q
web-check:
	cd web && npm run lint && npx tsc --noEmit && npm run build
# The single gate: CI runs exactly these steps.
check: lint test web-check
dev:
	@echo "API:  uv run repopilot serve      (needs GEMINI_API_KEY or another provider key)"
	@echo "Web:  cd web && npm run dev"
