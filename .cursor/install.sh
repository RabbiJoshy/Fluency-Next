#!/usr/bin/env bash
# Cloud Agent bootstrap for Fluency-Next.
#
# Idempotent: safe to run repeatedly and against a partially prepared VM. It
# prepares the Python 3.12 venv, installs the package with the optional
# extras the test suite imports, and materialises the local French Speech
# pilot release into an external workspace so `fluency dev` has data to mount.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The workspace holds generated data and must live outside the code repo
# (the workspace doctor enforces code/data separation).
export FLUENCY_WORKSPACE="${FLUENCY_WORKSPACE:-$HOME/Fluency-Workspace}"

# `python3.12 -m venv` needs the ensurepip data shipped in python3.12-venv.
if ! python3.12 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

if [ ! -x ".venv/bin/python" ]; then
  python3.12 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
# Core package plus every extra the checked-in tests import (cognate phonetics
# via panphon, the Spanish WSD ML stack, and the pytest/scikit-learn dev tools).
.venv/bin/python -m pip install --editable ".[cognates,wsd-es,dev]"

# Prepare the external workspace and publish the deterministic 25-card pilot so
# the dev server has an active release to serve. Both steps are idempotent.
PYTHONPATH=src .venv/bin/python -m fluency workspace init --path "$FLUENCY_WORKSPACE"
PYTHONPATH=src .venv/bin/python -m fluency pilot build --workspace "$FLUENCY_WORKSPACE"

echo "Fluency-Next environment ready. Workspace: $FLUENCY_WORKSPACE"
