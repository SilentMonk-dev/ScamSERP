#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if [ ! -x .venv/bin/python ]; then
    "${PYTHON:-python3}" -m venv .venv
fi
.venv/bin/python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
if [ "${SCAMSERP_SKIP_INSTALL:-0}" != "1" ]; then
    if [ -f requirements.lock ]; then
        .venv/bin/python -m pip install -r requirements.lock
        .venv/bin/python -m pip install --no-deps .
    else
        .venv/bin/python -m pip install .
    fi
fi
printf '%s\n' 'Starting ScamSERP. Default address: http://127.0.0.1:8000 (Ctrl+C stops the server).'
exec .venv/bin/python -m scamserp.cli serve "$@"
