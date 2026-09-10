.DEFAULT_GOAL := help
.PHONY: help install app calibrate run tune cameras login login-off test clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Create the venv and install everything
	uv sync

app:  ## Launch the menu bar app (macOS)
	uv run konsent-app

login:  ## Start the menu bar app automatically at login
	uv run python -c 'from konsent.autostart import enable; print("enabled:", enable())'

login-off:  ## Stop starting at login
	uv run python -c 'from konsent.autostart import disable; disable(); print("disabled")'

calibrate:  ## Measure your neutral head pose (run once per camera setup)
	uv run konsent --calibrate

run:  ## Start the virtual camera in the terminal
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
