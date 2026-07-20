#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve.py -- Startet das Sektor-Regime-Terminal lokal im Browser.

Ablauf:
  1. (optional) Daten via update_terminal.py frisch holen  (--no-update deaktiviert das)
  2. lokalen Webserver auf http://localhost:PORT starten
  3. Terminal-Seite im Browser oeffnen (bevorzugt Chrome)  (--no-browser deaktiviert das)

Vorteil gegenueber Doppelklick (file://): ueber http://localhost kann die Seite
die vom Update-Skript geschriebene livedata.json direkt nachladen (bei file://
blockt Chrome diesen Zugriff, dann greifen die eingebetteten Werte).

Aufruf:   python serve.py            (Port 8000, mit Update, oeffnet Browser)
          python serve.py --port 8765 --no-update
          python serve.py --no-browser
Beenden:  Strg+C
"""

import argparse
import os
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "sektor-regime-terminal.html"


def try_update():
    try:
        import update_terminal
        print("[serve] Hole aktuelle Daten (FRED) ...")
        update_terminal.main([])   # [] = eigene CLI-Argumente nicht durchreichen
    except Exception as e:
        print("[serve] Update uebersprungen ({}: {}) -- nutze vorhandene Werte.".format(
            type(e).__name__, e))


def open_browser(url):
    # Bevorzugt Chrome/Chromium, sonst Standardbrowser.
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser"):
        try:
            webbrowser.get(name).open_new(url)
            return
        except webbrowser.Error:
            continue
    try:
        webbrowser.open_new(url)
    except Exception:
        print("[serve] Konnte Browser nicht automatisch oeffnen.")


def main():
    ap = argparse.ArgumentParser(description="Sektor-Regime-Terminal lokal servieren.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-update", action="store_true", help="Daten NICHT vorab aktualisieren")
    ap.add_argument("--no-browser", action="store_true", help="Browser NICHT automatisch oeffnen")
    args = ap.parse_args()

    if not args.no_update:
        try_update()

    handler = partial(SimpleHTTPRequestHandler, directory=HERE)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as e:
        print("[serve] Port {} belegt ({}). Anderen Port waehlen: --port <n>".format(args.port, e))
        return 1

    url = "http://localhost:{}/{}".format(args.port, PAGE)
    print("[serve] Laeuft auf {}".format(url))
    print("[serve] Beenden mit Strg+C.")
    if not args.no_browser:
        threading.Timer(0.6, lambda: open_browser(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] Beendet.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
