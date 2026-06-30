\# Setup-Plan: Claude Code Memory Layer für PhD Lab



Dieses Dokument enthält die Architektur und alle Datei-Vorlagen, um Claude Code über mehrere Wochen hinweg ein stabiles Gedächtnis für das PhD-Laborprojekt zu geben. Das Setup verbindet dein privates Repository (`esibd\_bs`) mit dem öffentlichen Framework (`ESIBD Explorer`), ohne deren Git-Strukturen zu verändern.



\---



\## 1. Die neue Ordnerstruktur



Erstelle einen gemeinsamen Überordner (z. B. `phd\_lab/`). Platziere dort die beiden Repositories sowie den neuen, versteckten Speicher-Ordner `.claude\_memory/`.



```text

phd\_lab/                 <-- Hier startest du ab jetzt im Terminal "claude-code"

│

├── .claude\_memory/      <-- DAS GEMEINSAME LANGZEITGEDÄCHTNIS

│   ├── system\_instructions.md

│   ├── hardware\_map.md

│   └── architecture\_core.md

├── CLAUDE.md            <-- Die automatische Einstiegsdatei für Claude Code

│

├── esibd\_bs/            <-- DEIN PRIVATES REPO (Treiber \& Test-Notebooks)

│   ├── devices/         # Hier liegen deine Python-Geräteklassen

│   │   ├── \_\_init\_\_.py

│   │   ├── pump.py

│   │   └── spectrometer.py

│   ├── standalone/      # Deine neuen, unabhängigen Skripte (z.B. Nachtmessungen)

│   └── testing\_notebooks/ # Archivierte Jupyter-Notebooks zum Testen

│

└── ESIBD Explorer/      <-- DAS PUBLIC REPO (Unveränderte Struktur)

&#x20;   ├── core/            # Hauptcode des Explorers

&#x20;   └── plugins/         # HIER liegen deine Plugins

&#x20;       ├── plugin\_pump.py  # Importiert aus: esibd\_bs.devices.pump

&#x20;       └── plugin\_spec.py

```



\*Wichtiger Git-Hinweis:\* Füge `.claude\_memory/` und `CLAUDE.md` in die `.gitignore`-Dateien deiner jeweiligen Repositories ein, damit dein Speicher nicht versehentlich auf GitHub hochgeladen wird.



\---



\## 2. Die Datei-Vorlagen (Inhalte für deine Memory-Files)



Erstelle die folgenden Dateien im Hauptverzeichnis `phd\_lab/` bzw. im Ordner `.claude\_memory/` mit exakt diesem Inhalt:



\### Vorlage 1: `phd\_lab/CLAUDE.md`

```markdown

\# PhD Lab Automation Project - Multi-Repo Controller



Dieses Projekt besteht aus zwei getrennten Repositories:

1\. `esibd\_bs/`: Private Treiber (Geräteklassen) und Standalone-Programme.

2\. `ESIBD Explorer/`: Öffentliches Steuerungs-Framework (nutzt Plugins, die Treiber aus `esibd\_bs` importieren).



\## 🚀 INITIALISIERUNG (Bei JEDEM Session-Start ausführen)

1\. Lies sofort `.claude\_memory/system\_instructions.md` für deine Rolle und Programmierregeln.

2\. Lies `.claude\_memory/hardware\_map.md`, um den Status der physischen Geräte zu kennen.

3\. Lies `.claude\_memory/architecture\_core.md`, um zu sehen, woran wir aktuell arbeiten.



\## 🛑 SESSION-ENDE PROTOKOLL (Vor /clear oder dem Beenden)

1\. Aktualisiere den Fortschritt und offene Bugs in `.claude\_memory/architecture\_core.md`.

2\. Schreibe unter "Letzte Session-Notizen" exakt auf, wo die nächste Session nahtlos ansetzen muss.

```



\### Vorlage 2: `phd\_lab/.claude\_memory/system\_instructions.md`

```markdown

\# System-Anweisungen für Claude Code



\## Rolle

Du bist ein Senior-Entwickler für Laborautomatisierung und hardwarenahe Python-Programmierung. Du schreibst robusten, fehlertoleranten Code. Exception Handling ist kritisch, da Hardware im Labor unerwartet offline gehen oder blockieren kann.



\## Entwicklungs-Regeln

\- \*\*Threading \& Asynchronität:\*\* Laborgeräte blockieren oft bei langen Messungen oder Wartezeiten. Nutze sauberes Threading oder `asyncio`, um die GUI/Hauptsteuerung nicht einzufrieren.

\- \*\*Logging statt Prints:\*\* Jede Geräte-Interaktion (Senden, Empfangen, Timeouts) MUSS sauber protokolliert werden. Nutze Pythons `logging`-Modul, keine nackten `print()` Befehle.

\- \*\*Keine Blind-Generierung:\*\* Reflektiere erst über Hardware-Limits (Baudraten, Puffer, Timeouts), bevor du Code schreibst.

```



\### Vorlage 3: `phd\_lab/.claude\_memory/hardware\_map.md`

```markdown

\# Laborgeräte \& Python-Wrapper Register



\*Dieses Dokument wird von dir und Claude gepflegt, sobald neue Geräte hinzukommen oder Hardware-Bugs/Tricks entdeckt werden.\*



\## 1. Gerät: \[Beispiel: Spritzenpumpe / Syringe Pump]

\- \*\*Wrapper-Klasse:\*\* `esibd\_bs/devices/pump.py -> SyringePump`

\- \*\*Verbindung:\*\* Seriell (RS232 über USB-Adapter), Baudrate 9600.

\- \*\*Tücken / Hardware-Bugs:\*\* Benötigt nach jedem Fahrbefehl zwingend `time.sleep(0.5)`, sonst läuft der interne Gerätepuffer über und Befehle gehen verloren.

\- \*\*Status:\*\* Funktioniert im ESIBD Explorer Plugin, muss für Standalone-Skripte importiert werden.



\## 2. Gerät: \[Beispiel: Spektrometer]

\- \*\*Wrapper-Klasse:\*\* `esibd\_bs/devices/spectrometer.py -> OceanSpectrometer`

\- \*\*Verbindung:\*\* USB via nativem C-Treiber (ctypes).

\- \*\*Tücken / Hardware-Bugs:\*\* Wenn die Initialisierung fehlschlägt, muss der USB-Port physisch neu gesteckt werden. Stürzt bei Langzeitmessungen nach ca. 2 Stunden ohne Error-Meldung ab.

\- \*\*Status:\*\* Wrapper existiert, Langzeit-Stabilität muss debuggt werden.

```



\### Vorlage 4: `phd\_lab/.claude\_memory/architecture\_core.md`

```markdown

\# Architektur \& Projekt-Fortschritt



\## Import-Architektur (Die Brücke)

\- Die Plugins in `ESIBD Explorer/plugins/` enthalten KEINEN eigenen Hardware-Code.

\- Sie importieren die Klassen direkt aus `esibd\_bs/devices/` (z.B. `from esibd\_bs.devices.pump import SyringePump`).

\- Standalone-Programme in `esibd\_bs/standalone/` nutzen exakt dieselben Klassen.

\- Wichtig: Jede Änderung an einer Geräteklasse muss abwärtskompatibel mit den Explorer-Plugins UND den Standalone-Skripten sein!



\## Aktueller Sprint \& Task-Liste

\- \[ ] Refactoring: Alle alten Test-Notebooks sichten und die finalen Geräteklassen sauber nach `esibd\_bs/devices/` überführen.

\- \[ ] Import-Pfade prüfen: Sicherstellen, dass der `ESIBD Explorer` den `esibd\_bs`-Ordner im Python-Pfad findet.

\- \[ ] Erstes Standalone-Skript für eine automatisierte Nachtmessung in `esibd\_bs/standalone/` erstellen.



\## Letzte Session-Notizen (Wichtig für den Neustart)

\- \*\*Datum:\*\* 2026-06-30

\- \*\*Erreicht:\*\* Struktur für das zweigeteilte Projekt und den Markdown-Memory-Layer aufgesetzt.

\- \*\*Nächster Schritt:\*\* Claude Code muss gestartet werden, um die bestehenden Imports und Pfade in einem deiner aktuellen Plugins zu analysieren, damit die Brücke fehlerfrei steht.

```



\---



\## 3. Der tägliche Workflow mit Claude Code



1\. \*\*Session starten:\*\* 

&#x20;  Öffne dein Terminal im Überordner `phd\_lab/`, starte `claude-code` und tippe:

&#x20;  > \*"Lade den Kontext via CLAUDE.md. Sag mir, was laut architecture\_core.md unsere nächste Aufgabe ist."\*



2\. \*\*Gezielte Arbeitsanweisungen geben:\*\*

&#x20;  > \*"Schreibe ein neues Skript in `esibd\_bs/standalone/night\_run.py`. Nutze die Treiberklasse aus `esibd\_bs/devices/pump.py`. Achte darauf, das bestehende Plugin im Explorer nicht zu beschädigen."\*



3\. \*\*Der Gehirn-Reset (Context-Bereinigung bei zähen Sessions):\*\*

&#x20;  Wenn der Chat zu lang wird, Fehlermeldungen sich häufen und Claude Fehler macht:

&#x20;  - \*\*Schritt A:\*\* \*"Claude, aktualisiere `.claude\_memory/architecture\_core.md`. Halte fest, welche Code-Änderungen wir gemacht haben und wo wir gerade festhängen."\*

&#x20;  - \*\*Schritt B:\*\* Tippe im Terminal den Befehl `/clear`, um den Chat-Token-Zähler auf 0 zu setzen.

&#x20;  - \*\*Schritt C:\*\* Spüle das Gedächtnis wieder ein: \*"Lade den Kontext neu über CLAUDE.md. Lass uns an der dokumentierten Stelle weitermachen."\*



