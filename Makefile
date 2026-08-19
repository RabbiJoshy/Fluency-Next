PYTHON ?= python3.12
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
RUN_PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(PYTHON))

.PHONY: bootstrap test dev clean-venv

bootstrap:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable .

test:
	PYTHONPATH=src $(RUN_PYTHON) -m unittest discover -s tests -v

dev:
	PYTHONPATH=src $(RUN_PYTHON) -m fluency dev

clean-venv:
	$(PYTHON) -c 'import shutil; shutil.rmtree(".venv", ignore_errors=True)'
