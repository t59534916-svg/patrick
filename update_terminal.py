#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_terminal.py -- Auto-Updater fuer das Sektor-Regime-Terminal.

Holt die aktuellen US-Makrodaten direkt von FRED (Federal Reserve Economic Data,
St. Louis Fed), berechnet die Modell-Eingaben und schreibt sie in
  - livedata.json                (fuer die per localhost geoeffnete Seite)
  - sektor-regime-terminal.html  (eingebetteter <script id="livedata">-Block,
                                  fuer den direkten Datei-Aufruf per Doppelklick)

Serverseitiger Abruf = keine CORS-Proxys noetig (im Gegensatz zum Browser, wo
FRED mangels CORS-Headern nur ueber wackelige Proxys erreichbar ist).
Nur Python-Standardbibliothek, keine Installation noetig (Python >= 3.8).

Manuell gepflegte Felder (ISM, ISM-Delta, Fed-Bias) werden aus der bestehenden
Datei uebernommen und NICHT ueberschrieben -- diese stammen aus Monats-Releases
bzw. FOMC-Entscheiden. Dauerhaft setzen laesst sich so ein Feld per

    python update_terminal.py --no-fetch --set ism=49.8 --set fedBias=0

(--no-fetch: nur schreiben, kein FRED-Abruf; ohne --no-fetch wird zusaetzlich
aktualisiert). Eingaben in der Browser-Oberflaeche gelten dagegen nur fuer die
laufende Sitzung.

Per Cron / Aufgabenplaner regelmaessig aufrufen (siehe README.md).
"""

import argparse
import json
import os
import re
import ssl
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(HERE, "sektor-regime-terminal.html")
JSON_FILE = os.path.join(HERE, "livedata.json")

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={cosd}"
TIMEOUT = 30

# Serien-Definitionen: key -> (FRED-ID, Lookback-Tage fuer den CSV-Abruf)
SERIES = {
    "cpi":  ("CPIAUCSL",   900),   # VPI (alle Verbraucher)   -> y/y
    "core": ("CPILFESL",   900),   # Kern-VPI                 -> y/y
    "nfp":  ("PAYEMS",     900),   # Beschaeftigte (Tsd.)     -> Monats-Delta
    "ry":   ("DFII10",     400),   # 10J TIPS-Realzins        -> Trend 28T
    "oil":  ("DCOILWTICO", 400),   # WTI Rohoel               -> Trend 90T
    "vix":  ("VIXCLS",    3700),   # VIX                      -> Niveau + Perzentil
}

# Defaults fuer manuell gepflegte Felder (nur falls in der Datei nichts steht)
MANUAL_DEFAULTS = {"ism": 53.3, "ismDelta": -0.7, "fedBias": 1}
# Per --set aenderbare Felder und ihr Typ (fedBias zusaetzlich auf -1/0/1 geprueft)
MANUAL_KEYS = {"ism": float, "ismDelta": float, "fedBias": int}


# ---------------------------------------------------------------------------
# Abruf & Parsing
# ---------------------------------------------------------------------------
def fetch_text(url):
    """CSV von FRED holen. Nutzt System-CAs bzw. SSL_CERT_FILE und respektiert
    HTTPS_PROXY automatisch (Standard-Opener von urllib)."""
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": "sektor-regime-terminal/1.0"})
    with urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        text = resp.read().decode("utf-8", "replace")
    if len(text) < 20 or "<html" in text.lower():
        raise ValueError("unerwartete Antwort (kein CSV)")
    return text


def parse_fred(csv):
    """FRED-CSV -> Liste [(datum, wert), ...]; fehlende Werte ('.') werden uebersprungen."""
    out = []
    for line in csv.splitlines():
        c = [x.strip() for x in line.split(",")]
        if len(c) != 2 or c[0] in ("DATE", "observation_date"):
            continue
        try:
            v = float(c[1])
        except ValueError:
            continue
        out.append((c[0], v))
    if not out:
        raise ValueError("FRED leer")
    return out


def fred_url(fid, days):
    cosd = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return FRED_CSV.format(id=fid, cosd=cosd)


# ---------------------------------------------------------------------------
# Kennzahl-Berechnung (spiegelt die Browser-Logik in sektor-regime-terminal.html)
# ---------------------------------------------------------------------------
def _to_date(s):
    return datetime.strptime(s[:10], "%Y-%m-%d")


def yoy(rows):
    """Jahresveraenderung in Prozent (auf 1 Nachkommastelle), Referenz = naechster
    Datenpunkt ~12 Monate vor dem letzten."""
    ld, lv = rows[-1]
    target = "{}{}".format(int(ld[:4]) - 1, ld[4:10])
    td = _to_date(target)
    best, bd = rows[0], None
    for r in rows:
        d = abs((_to_date(r[0]) - td).days)
        if bd is None or d < bd:
            bd, best = d, r
    return round((lv / best[1] - 1) * 1000) / 10.0


def trend(rows, lb_days, band):
    """Richtung ueber lb_days: +1 steigend / 0 seitwaerts / -1 fallend,
    relativ zur Bandbreite 'band'."""
    ld, lv = rows[-1]
    t = _to_date(ld) - timedelta(days=lb_days)
    best, bd = rows[0], None
    for r in rows:
        d = abs((_to_date(r[0]) - t).days)
        if bd is None or d < bd:
            bd, best = d, r
    base = abs(best[1]) or 1.0
    ch = (lv - best[1]) / base
    return 1 if ch > band else (-1 if ch < -band else 0)


# ---------------------------------------------------------------------------
# Sammeln
# ---------------------------------------------------------------------------
def load_existing():
    """Bestehende eingebettete Werte laden (fuer manuelle Felder + Fallback)."""
    if not os.path.exists(HTML_FILE):
        return {}
    try:
        with open(HTML_FILE, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'<script id="livedata"[^>]*>(.*?)</script>', html, re.S)
        if m:
            return json.loads(m.group(1).strip())
    except Exception:
        pass
    return {}


def collect():
    prev = load_existing()
    j = dict(prev)          # mit alten Werten starten -> Teilausfaelle behalten alte Daten
    errs = []
    ok = [0]                # Zaehler erfolgreicher Abrufe

    def grab(key, fn):
        fid, days = SERIES[key]
        try:
            rows = parse_fred(fetch_text(fred_url(fid, days)))
            fn(rows)
            ok[0] += 1
        except (URLError, HTTPError, ValueError, OSError) as e:
            errs.append("{} ({})".format(fid, e.__class__.__name__))

    def set_cpi(rows):
        j["cpi"] = yoy(rows)
        older = rows[:-3]
        if len(older) > 15:
            d = j["cpi"] - yoy(older)
            j["cpiTrend"] = 1 if d > 0.15 else (-1 if d < -0.15 else 0)

    def set_core(rows):
        j["core"] = yoy(rows)

    def set_nfp(rows):
        if len(rows) >= 2:
            j["nfp"] = round(rows[-1][1] - rows[-2][1])

    def set_ry(rows):
        j["realYield"] = trend(rows, 28, 0.03)

    def set_oil(rows):
        j["oilTrend"] = trend(rows, 90, 0.05)

    def set_vix(rows):
        vals = [v for _, v in rows]
        cur = vals[-1]
        j["vix"] = round(cur * 10) / 10.0
        j["vixPct"] = round(sum(1 for v in vals if v <= cur) / len(vals) * 100) / 100.0

    grab("cpi", set_cpi)
    grab("core", set_core)
    grab("nfp", set_nfp)
    grab("ry", set_ry)
    grab("oil", set_oil)
    grab("vix", set_vix)

    # Manuell gepflegte Felder erhalten bzw. Default setzen
    for k, dv in MANUAL_DEFAULTS.items():
        j.setdefault(k, dv)

    got = ok[0]
    j["source"] = "auto" if got else prev.get("source", "eingebettet")
    j["asOf"] = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    return j, errs, got


# ---------------------------------------------------------------------------
# Schreiben (atomar)
# ---------------------------------------------------------------------------
def atomic_write(path, text):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_json(j):
    atomic_write(JSON_FILE, json.dumps(j, ensure_ascii=False, indent=2) + "\n")


def write_html(j):
    """Eingebetteten <script id="livedata">-Block ersetzen (Funktions-Replacement,
    damit JSON-Inhalt nicht als Regex-Backreference interpretiert wird)."""
    if not os.path.exists(HTML_FILE):
        return False
    with open(HTML_FILE, encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(j, ensure_ascii=False)
    new_html, n = re.subn(
        r'(<script id="livedata"[^>]*>)(.*?)(</script>)',
        lambda m: m.group(1) + "\n" + payload + "\n" + m.group(3),
        html, count=1, flags=re.S)
    if n:
        atomic_write(HTML_FILE, new_html)
    return bool(n)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_sets(pairs):
    """--set FELD=WERT validieren -> dict. Bricht mit Exit-Code 2 bei Fehlern ab."""
    out = {}
    for p in pairs:
        if "=" not in p:
            sys.exit("Fehler: --set erwartet FELD=WERT, bekam: {!r}".format(p))
        k, v = p.split("=", 1)
        if k not in MANUAL_KEYS:
            sys.exit("Fehler: --set kennt nur {} (bekam: {!r})".format(
                ", ".join(sorted(MANUAL_KEYS)), k))
        try:
            val = MANUAL_KEYS[k](v)
        except ValueError:
            sys.exit("Fehler: ungueltiger Wert fuer {}: {!r}".format(k, v))
        if k == "fedBias" and val not in (-1, 0, 1):
            sys.exit("Fehler: fedBias muss -1, 0 oder 1 sein (bekam: {})".format(val))
        out[k] = val
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Aktualisiert das Sektor-Regime-Terminal mit FRED-Daten.")
    ap.add_argument("--set", action="append", default=[], metavar="FELD=WERT",
                    help="manuelles Feld dauerhaft setzen ({}); mehrfach nutzbar".format(
                        ", ".join(sorted(MANUAL_KEYS))))
    ap.add_argument("--no-fetch", action="store_true",
                    help="kein FRED-Abruf; nur --set anwenden und Dateien schreiben")
    args = ap.parse_args(argv)
    overrides = parse_sets(args.set)

    if args.no_fetch:
        j = load_existing()
        for k, dv in MANUAL_DEFAULTS.items():
            j.setdefault(k, dv)
        errs, got = [], 0
        if overrides:
            j["asOf"] = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    else:
        j, errs, got = collect()
    j.update(overrides)

    write_json(j)
    html_ok = write_html(j)

    stamp = j.get("asOf", "?")
    if args.no_fetch:
        msg = "OK   kein Abruf (--no-fetch) - Stand {}".format(stamp)
    elif got:
        msg = "OK   {}/6 Serien aktualisiert - Stand {}".format(got, stamp)
    else:
        msg = "WARN keine Serie erreichbar - alte Werte behalten - Stand {}".format(stamp)
    if overrides:
        msg += " - gesetzt: " + ", ".join("{}={}".format(k, v) for k, v in overrides.items())
    if errs:
        msg += " - Fehler: " + ", ".join(errs)
    if not html_ok:
        msg += " - (HTML-Block nicht gefunden)"
    print(msg)
    print("     cpi={} core={} nfp={} vix={} cpiTrend={} oilTrend={} realYield={} "
          "ism={} fedBias={}".format(
              j.get("cpi"), j.get("core"), j.get("nfp"), j.get("vix"),
              j.get("cpiTrend"), j.get("oilTrend"), j.get("realYield"),
              j.get("ism"), j.get("fedBias")))
    return 0 if (got or args.no_fetch) else 1


if __name__ == "__main__":
    sys.exit(main())
