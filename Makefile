.DEFAULT_GOAL := help
.PHONY: help install calibrate run tune cameras test clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Create the venv and install everything
	uv sync

calibrate:  ## Measure your neutral head pose (run once per camera setup)
	uv run konsent --calibrate

run:  ## Start the virtual camera
	uv run konsent

tune:  ## Preview window with live threshold readouts
	uv run konsent --preview --hud

cameras:  ## List available cameras
	uv run konsent --list-cameras

test:  ## Run the test suite
	uv run pytest -q

clean:  ## Remove the venv, caches and downloaded model
	rm -rf .venv .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf "$${XDG_CACHE_HOME:-$$HOME/Library/Caches}/konsent"
