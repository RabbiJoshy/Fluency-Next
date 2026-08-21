PYTHON ?= python3.12
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
RUN_PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(PYTHON))
FLUENCY_WORKSPACE ?= /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace

.PHONY: bootstrap test pilot dev clean-venv

bootstrap:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable .

test:
	PYTHONPATH=src $(RUN_PYTHON) -m unittest discover -s tests -v

pilot:
	PYTHONPATH=src $(RUN_PYTHON) -m fluency pilot build --workspace $(FLUENCY_WORKSPACE)

dev:
	PYTHONPATH=src $(RUN_PYTHON) -m fluency dev --workspace $(FLUENCY_WORKSPACE)

clean-venv:
	$(PYTHON) -c 'import shutil; shutil.rmtree(".venv", ignore_errors=True)'
