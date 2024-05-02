# Project management tasks.

VENV = .venv
PYTHON = . $(VENV)/bin/activate && python

$(VENV)/.make-update: requirements.txt
	python -m venv $(VENV)
	$(PYTHON) -m pip install -U pip -r $^
	touch $@

.PHONY: dev
dev: $(VENV)/.make-update

.PHONY: build
build: dev
	$(PYTHON) build.py
