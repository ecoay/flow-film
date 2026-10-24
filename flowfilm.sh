#!/usr/bin/env bash
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec python3 -c "import sys; sys.path.insert(0, '$DIR'); from flowfilm.cli import main; main()" "$@"
