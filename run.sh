#!/usr/bin/env sh
set -eu

project_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_directory"

venv_python="$project_directory/.venv/bin/python"

is_compatible_python() {
    "$@" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1
}

if [ -x "$venv_python" ]; then
    if ! is_compatible_python "$venv_python"; then
        echo "The existing .venv uses an incompatible Python version."
        echo "Delete the .venv directory and run this script again."
        exit 1
    fi
else
    python_command=""
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && is_compatible_python "$candidate"; then
            python_command=$candidate
            break
        fi
    done

    if [ -z "$python_command" ]; then
        echo "Luculent requires Python 3.10, 3.11, 3.12, or 3.13."
        echo "Install a compatible version using your Linux distribution and try again."
        exit 1
    fi

    echo "Creating Luculent's virtual environment..."
    "$python_command" -m venv .venv
fi

echo "Installing Luculent's requirements..."
"$venv_python" -m pip install -r requirements.txt

echo "Starting Luculent on an available local port..."
"$venv_python" -m app.web --open-browser
