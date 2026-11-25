.PHONY: install lint test web-check check dev eval eval-verify
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
# Checks the dataset ground truth against the pinned repos (needs network, no LLM key).
eval-verify:
	uv run repopilot eval verify
# Full evaluation with the configured provider (REPOPILOT_PROVIDER plus its key). Slow on free tiers.
# Usage: make eval LABEL=baseline
LABEL ?= run
eval:
	uv run repopilot eval run $(LABEL) --min-interval 2
	uv run repopilot eval report evals/results/$(LABEL)
