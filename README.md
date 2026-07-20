# Sektor-Regime-Terminal — automatisiert aktualisierend

Ein Investment-Clock-Dashboard: Aus US-Makrodaten (ISM, CPI, Nonfarm Payrolls,
VIX, Fed-Bias, 10J-Realzins, Ölpreis) klassifiziert es das Marktregime
(Goldilocks / Überhitzung / Stagflation / Rezession / Zinsschock) und leitet
daraus relative Sektor-Signale (Long/Short) und Spread-Paare ab.

Diese Version **hält sich automatisch aktuell** und ist **lokal** (Doppelklick
oder lokaler Server) **oder im Browser** (auch online) aufrufbar.

> Keine Anlageberatung. Relative, schematische Signale — kein Markt-Timing.

---

## Dateien

| Datei | Zweck |
|---|---|
| `sektor-regime-terminal.html` | Das Terminal (öffnet im Browser, rechnet lokal). |
| `update_terminal.py` | Holt aktuelle FRED-Daten und schreibt sie in `livedata.json` **und** in den eingebetteten Block der HTML. **Kern der Automatik.** |
| `livedata.json` | Zuletzt abgerufener Datenstand (wird vom Server-Modus geladen). |
| `serve.py` | Startet lokalen Server + öffnet das Terminal im Browser. |
| `run_update.sh` / `run_update.bat` | Wrapper für Cron (Linux/macOS) bzw. Aufgabenplaner (Windows). |
| `.github/workflows/update.yml` | Optional: aktualisiert die Daten online per GitHub Actions. |

**Voraussetzung:** Python ≥ 3.8. **Keine** Installation nötig (nur Standardbibliothek).

---

## Welche Daten sind automatisch, welche manuell?

**Automatisch von FRED** (St. Louis Fed, keine Registrierung/kein Key nötig):

| Feld | FRED-Serie | Ableitung |
|---|---|---|
| CPI y/y | `CPIAUCSL` | Jahresveränderung |
| Kern-CPI y/y | `CPILFESL` | Jahresveränderung |
| CPI-Trend (3M) | `CPIAUCSL` | Vergleich aktuelle vs. 3M-alte y/y |
| Nonfarm Payrolls | `PAYEMS` | Monatsdelta (Tsd.) |
| 10J-Realzins-Richtung | `DFII10` | Trend über 28 Tage |
| Ölpreis-Trend | `DCOILWTICO` | Trend über 90 Tage |
| VIX | `VIXCLS` | Niveau + Perzentil |

**Manuell gepflegt** (aus Monats-Releases / FOMC — werden vom Skript **nicht**
überschrieben): **ISM-Niveau**, **ISM-Δ**, **Fed-Bias**. Diese direkt in der
Oberfläche ändern; die Werte bleiben beim nächsten Auto-Update erhalten.

---

## Nutzung

### A) Lokal per Doppelklick (am einfachsten)

`sektor-regime-terminal.html` doppelklicken → öffnet im Standardbrowser.
Es zeigt die zuletzt vom Skript geschriebenen (eingebetteten) Werte und rechnet
sofort. Alle Eingaben sind editierbar.

> Beim direkten Datei-Aufruf (`file://`) blockt Chrome aus Sicherheitsgründen
> das Nachladen von `livedata.json`. Das ist unkritisch: Das Update-Skript
> schreibt die Werte **zusätzlich** direkt in die HTML, sie sind also beim
> Öffnen bereits aktuell. Für live nachladbare Daten Variante **B**.

### B) Lokal per Server (empfohlen für „im Chrome")

```bash
python serve.py
```

Das holt zuerst frische Daten, startet `http://localhost:8000` und öffnet das
Terminal (bevorzugt in Chrome). Über `http://localhost` kann die Seite
`livedata.json` direkt nachladen und aktualisiert sich alle 30 Minuten selbst.

```bash
python serve.py --port 8765     # anderer Port
python serve.py --no-update     # ohne Vorab-Abruf starten
python serve.py --no-browser    # Server ohne Browser-Autostart
```

Beenden mit `Strg+C`.

---

## Automatisch aktuell halten

Das Terminal versucht beim Öffnen selbst zu aktualisieren, aber der **Browser**
erreicht FRED nur über wackelige CORS-Proxys. **Zuverlässig** ist der Weg über
`update_terminal.py` (serverseitiger Abruf, keine Proxys). Einmal einrichten:

### Linux / macOS (Cron)

`run_update.sh` ist ausführbar (sonst `chmod +x run_update.sh`). Dann:

```bash
crontab -e
```

Zeile hinzufügen (Pfad anpassen) — z. B. stündlich:

```
0 * * * * /ABSOLUTER/PFAD/zu/run_update.sh
```

Oder einmal werktags um 18:30 nach US-Schluss:

```
30 18 * * 1-5 /ABSOLUTER/PFAD/zu/run_update.sh
```

Das Log landet in `update.log` im selben Ordner.

<details>
<summary>macOS-Alternative: launchd</summary>

Eine `~/Library/LaunchAgents/com.terminal.update.plist` mit
`ProgramArguments` = `["/ABSOLUTER/PFAD/run_update.sh"]` und
`StartInterval` = `3600`, dann `launchctl load …plist`.
</details>

### Windows (Aufgabenplaner)

```
schtasks /Create /SC HOURLY /TN "Sektor-Regime-Update" ^
  /TR "C:\PFAD\zu\run_update.bat"
```

Oder grafisch: Aufgabenplaner → *Aufgabe erstellen* → Trigger (z. B. stündlich)
→ Aktion: Programm `run_update.bat`. Log in `update.log`.

### Prüfen, ob es läuft

```bash
python update_terminal.py
```

Erwartete Ausgabe etwa:

```
OK   6/6 Serien aktualisiert - Stand 20.07.2026 18:30
     cpi=3.5 core=2.6 nfp=57 vix=18.8 cpiTrend=1 oilTrend=-1 realYield=1 ...
```

Bei Teilausfall bleiben die jeweils alten Werte erhalten; die Kopfzeile im
Terminal zeigt den Datenstand.

---

## C) Optional: online im Browser (überall erreichbar)

Damit das Terminal **ohne laufenden lokalen Rechner** aktuell bleibt und von
jedem Gerät im Browser abrufbar ist:

1. Repo zu GitHub pushen (ist bereits eingerichtet).
2. **GitHub Pages** aktivieren: *Settings → Pages → Source: Branch `main`*.
   Danach ist das Terminal unter
   `https://<user>.github.io/<repo>/sektor-regime-terminal.html` erreichbar.
3. Der Workflow `.github/workflows/update.yml` läuft (nach dem Merge in `main`)
   werktags automatisch, holt frische FRED-Daten und committet sie. Manuell
   auslösbar unter *Actions → „Terminal-Daten aktualisieren" → Run workflow*.
   Zeitplan (`cron:`) in der Datei nach Bedarf anpassen.

Auf GitHub Pages lädt die Seite `livedata.json` sauber nach (gleiche Herkunft) —
der Datenstand entspricht dem letzten Workflow-Lauf.

---

## Wie die Engine rechnet (Kurzfassung)

- **Wachstum G** aus ISM-Niveau, ISM-Δ und Payrolls.
- **Inflation I** aus CPI vs. 2 %-Ziel, Kernrate, CPI- und Öl-Trend.
- **Zinsimpuls Z** aus Fed-Bias und Realzins-Richtung.
- Daraus Quadranten-Gewichte (Goldilocks/Überhitzung/Stagflation/Rezession),
  überblendet mit einer **Zinsschock**-Spalte (Gewicht aus Z).
- **VIX > 28** dämpft alle Spreads (Korrelationskonvergenz).
- **Sektorscore** = Σ Regimegewicht × Matrixwert (−2…+2); Long ab +0.5,
  Short ab −0.5.

Details stehen im Panel „Engine-Logik" der Oberfläche. `update_terminal.py`
spiegelt exakt die FRED-Logik des Browser-Codes, holt die Daten aber
serverseitig.
