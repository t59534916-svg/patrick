#!/bin/sh
# Cron-/launchd-Wrapper fuer update_terminal.py (Linux/macOS).
# Wechselt ins Skriptverzeichnis und loggt nach update.log.
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "$(date): kein Python gefunden" >> "$DIR/update.log"
  exit 1
fi
{
  echo "----- $(date) -----"
  "$PY" "$DIR/update_terminal.py"
} >> "$DIR/update.log" 2>&1
