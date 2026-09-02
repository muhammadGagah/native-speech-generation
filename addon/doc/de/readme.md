# Natürliche Spracherzeugung für NVDA

**Autor:** Muhammad Gagah muha.aku@gmail.com **

Natürliche Spracherzeugung ist ein NVDA‑Add-on, das **Google Gemini AI** integriert, um hochwertige, natürlich klingende Sprache direkt in NVDA zu erzeugen.

Es bietet eine klare, vollständig zugängliche Oberfläche zur Umwandlung von Text in Audio und unterstützt sowohl **Einzelsprecher‑Vorlesemodi** als auch **dynamische Dialoge mit zwei Sprechern**.

Dieses Addon ist für reibungslose Arbeitsabläufe, barrierefreie Bedienung und flexible Stimmkontrolle ausgelegt – ideal für Vorlesetexte, Dialoge und Audio‑Content‑Produktion.

## Funktionen

### Hochwertige Spracherzeugung

* Auswahl zwischen:

  * **Gemini Flash** – Standardqualität, schnelle Erzeugung, geringe Latenz.
  * **Gemini Pro** – Premium, realistischere Stimmen (kostenpflichtiges Modell).

### Einzel- & Mehrsprecher-Modi

* **Einzelsprecher‑Modus** für klassisches Text‑zu‑Sprache.
* **Mehrsprecher‑Modus (2 Sprecher)** für Dialoge mit unterschiedlichen Stimmen.

### Erweiterte Stimmkontrolle

* **Sprechernamen**
  Weise im Mehrsprecher‑Modus individuelle Namen zu (z. B. *John*, *Mary*).
  Die KI ordnet Stimmen automatisch anhand der Namen im Skript zu.
* **Stil‑Anweisungen**
  Gib Hinweise wie *„Sprich in fröhlichem Ton“* oder *„Ruhig erzählen“*, um die Sprechweise zu steuern.
* **Kreativitäts-Regler**
  Steuert Variation und Kreativität:

  * Niedrige Werte → stabiler, vorhersehbarer.
  * Hohe Werte → ausdrucksstärker, variabler.

### Zugängliche & übersichtliche Oberfläche

* Vollständig screenreader‑freundlich.
* Erweiterte Optionen in einem ausklappbaren Bereich, damit der Hauptdialog übersichtlich bleibt.

### Nahtloser Arbeitsablauf

* Audio wird nach der Erzeugung automatisch abgespielt.
* Erzeugtes Audio kann erneut abgespielt oder als hochwertige `.wav`‑Datei gespeichert werden.
* Für wiederholte Nutzung optimiert.

### Intelligentes Laden & zwischenspeichern von Stimmen

* Verfügbare Stimmen werden dynamisch über die Gemini‑API geladen.
* Stimmen werden **24 Stunden** lang zwischengespeichert, um API‑Aufrufe zu reduzieren und den Start zu beschleunigen.

### Quick Speak

* **NVDA+Alt+E** liest den aktuell markierten Text sofort vor.
* **NVDA+Alt+Umschalt+E** liest Klartext aus der Zwischenablage vor.
* Die Audiowiedergabe erfolgt intern über das in NVDA konfigurierte Ausgabegerät, sodass der Fokus in der aktuellen Anwendung bleibt.
* Modell, Stimme, Lautstärke und Aussprache-/Stilanweisungen können für Quick Speak separat eingestellt werden.
* Die Quick-Speak-Lautstärke reicht von 0 (stumm) bis 100 (volle Lautstärke) und bleibt nach einem NVDA-Neustart erhalten.
* Der markierte Text oder Zwischenablagetext wird zur Audioerzeugung an Google Gemini gesendet.
* Gemini 3.1 Flash Live Preview wird für niedrige Latenz empfohlen. API-Kontingente und Live-Sitzungslimits gelten weiterhin. Der Dienst ist nicht unbegrenzt.
* Verfügbare Quick-Speak-Modelle sind Gemini 3.1 Flash Live Preview, Gemini 2.5 Flash Native Audio, Gemini 3.1 Flash TTS Preview, Gemini 2.5 Flash TTS Preview und Gemini 2.5 Pro TTS Preview. Für das Pro-Modell ist eine kostenpflichtige API erforderlich.
* Drücke einen der beiden Quick-Speak-Befehle erneut, um die aktive Anfrage oder Wiedergabe zu stoppen.

### Sprechen mit der KI (Live‑Konversation)

* **Echtzeit‑Sprachchat**: Führe ein natürliches Gespräch mit Gemini.
* **Verbindung mit Google-Suche**: Erlaube der KI, aktuelle Web‑Informationen abzurufen.
* **Unterbrechbar**: Du kannst die KI jederzeit stoppen – per Sprache oder „Stoppe Gespräch“.
* **Anpassbar**: Nutzt deine gewählte Stimme und Stil‑Anweisungen.
* **Denklevel‑Steuerung**: `No Thinking`, `Low`, `Medium`, `High`.
* **Wieder verbinden**: Jüngster Gesprächskontext wird nach Verbindungsabbruch automatisch wiederhergestellt.
* **Stabileres Streaming**: Verbesserte Wiederverbindung (Backoff + Retry) und adaptive Audiopufferung.

-## Voraussetzungen

* NVDA 2024.1 oder neuer. Getestet bis NVDA 2026.2.
* Aktive Internetverbindung
* Gültiger **Google Gemini API‑Schlüssel**

-## Installation

1. Lade das neueste Add-on von der
   **Veröffentlichungsseite:**
   `https://github.com/MuhammadGagah/native-speech-generation/releases`
2. Installiere es wie jedes NVDA‑Add-on.
3. Starte NVDA neu, wenn du dazu aufgefordert wirst.

-## API‑Schlüssel einrichten (erforderlich)

1. Erstelle einen API‑Schlüssel in **Google AI Studio**:
   <https://aistudio.google.com/apikey>
2. Öffne NVDA und gehe zu:
   **NVDA-Menü → Werkzeuge → Natürliche Spracherzeugung**
3. Klicke auf **„API Key Einstellungen“**.
4. Dadurch öffnet sich der NVDA‑Einstellungsdialog direkt im Bereich *Natürliche Spracherzeugung*.
5. Füge deinen **Gemini API‑Schlüssel** in das Feld *GEMINI API Key* ein.
6. Klicke auf **OK**, um zu speichern.

Gespeicherte Schlüssel werden sicher über **Windows DPAPI** verschlüsselt – sie können auf anderen Windows‑Systemen oder Benutzerkonten nicht entschlüsselt werden.

Für fortgeschrittene Bereitstellungen kannst du den Schlüssel auch über die Umgebungsvariable
**`GEMINI_API_KEY`** bereitstellen. Das Add-on nutzt ihn automatisch, wenn kein gespeicherter Schlüssel vorhanden ist.

## Verwendung

Öffne den Dialog über:

* **NVDA+Strg+Umschalt+G**, oder
* **NVDA-Menü → Werkzeuge → Natürliche Spracherzeugung**

### Hauptelemente der Oberfläche

* **Text zum Konvertieren**
  Gib den Text ein oder füge ihn ein.
* **Stil‑Anweisungen (optional)**
  Hinweise zu Ton, Emotion oder Sprechweise.
* **Modell auswählen**

  * Flash (Standardqualität)
  * Pro (Hohe Qualität)
* **Sprechermodus**

  * Einzelsprecher
  * Mehrsprecher (2)

## Spracherzeugung

### Quick Speak für markierten Text oder die Zwischenablage

1. Wähle unter **NVDA-Einstellungen -> Natürliche Spracherzeugung** Modell, Stimme, Lautstärke und optionale Aussprache-/Stilanweisungen aus.
2. Markiere Text und drücke **NVDA+Alt+E**, oder kopiere Text und drücke **NVDA+Alt+Umschalt+E**.
3. Die Sprache wird ohne Dialog und ohne Fokuswechsel wiedergegeben.
4. Drücke einen der Befehle erneut, um Quick Speak zu stoppen.

Start, Abschluss und Wiedergabe werden absichtlich nicht angesagt. Nur Fehler, die eine Aktion erfordern, werden gemeldet.

### Einzelsprecher‑Modus

1. Wähle **Einzelsprecher**.
2. Wähle eine Stimme aus der Liste.
3. Gib deinen Text ein.
4. Optional: Stil‑Anweisungen hinzufügen.
5. Klicke **Sprache erzeugen**.
6. Das Audio wird automatisch abgespielt.

### Mehrsprecher‑Modus

1. Wähle **Mehrsprecher (2)**.
2. Für jeden Sprecher:

   * Einen eindeutigen **Sprechernamen** eingeben.
   * Eine **Stimme** auswählen.

3. Text so formatieren, dass jede Zeile mit dem Sprechernamen und Doppelpunkt beginnt.

**Beispiel:**

```
Alice: Hallo Bob, wie geht es dir heute?
Bob: Mir geht’s super, Alice! Das Wetter ist fantastisch.
```

4. Klicke **Sprache erzeugen*.
   Stimmen werden automatisch anhand der Namen zugeordnet.

## Sprechen mit der KI (Live‑Modus)

Erlebe ein natürliches Sprachgespräch mit Gemini.

1. Stimme und Stil‑Anweisungen im Hauptdialog konfigurieren.
   *(Hinweis: Sprechen mit der KI unterstützt derzeit nur Einzelsprecher‑Modus.)*
2. Klicke **Sprechen mit der KI**.
3. Im neuen Fenster:

   * **Gespräch beginnen** – beginnt die Sitzung, Mikrofon aktiv.
   * **Gespräch stoppen** – beendet die Sitzung.
   * **Verbindung mit Google-Suche** – erlaubt Web‑Recherche.
     *(Während einer aktiven Sitzung ausgeblendet.)*
   * **Verarbeitungstiefe: ** – `Nein`, `Niedrig`, `Medium`, `Hoch`.
   * **Mikrofon‑Schalter** – Stummschalten/aktivieren.
   * **Lautstärke** – Wiedergabelautstärke der KI. Lautstärke sowie ausgewählte Ein- und Ausgabegeräte werden beim Schließen des Dialogs gespeichert.

## Erweiterte Einstellungen

* Aktiviere **Erweiterte Einstellungen (Kreativitäts-Regler)**, um den Regler anzuzeigen.
* **Bereich** für den Kreativitäts-Regler:

  * `0.0` → am stabilsten, deterministisch.
  * `1.0` → Standardbalance.
  * `2.0` → kreativste, variabelste Ausgabe.

## Übersicht der Schaltflächen

* **Sprache erzeugen** – Spracherzeugung starten.
* **Wiedergabe** – Letztes Audio erneut abspielen.
* **Sprechen mit der KI** – Echtzeit‑Konversationsfenster öffnen.
* **Audio speichern** – Audio als `.wav` speichern.
* **API Key Einstellungen** – API‑Schlüssel‑Einstellungen öffnen.
* **Stimmen in AI Studio anzeigen (Browser)** – Öffnet Google AI Studio im Browser.
* **Schließen** – Dialog schließen (`Escape`).

## Tastenkombinationen

Anpassbar unter:
**NVDA-Menü → Optionen → Tastenbefehle → Natürliche Spracherzeugung**

Standard:

* **NVDA+Strg+Umschalt+G** – Öffnet den Dialog.
* **NVDA+Alt+E** – Liest markierten Text mit Quick Speak oder stoppt Quick Speak.
* **NVDA+Alt+Umschalt+E** – Liest Zwischenablagetext mit Quick Speak oder stoppt Quick Speak.

Alle Befehle können in NVDA unter Tastenbefehle geändert oder entfernt werden.

## Entwicklung & Beitrag

Wenn du das Add-on Weiterentwickeln oder anpassen möchtest:

### Entwicklungsumgebung

* **Python passend zur Ziel-NVDA-Laufzeit**
  * Verwende **Python 3.13 64-bit** für NVDA 2026.1 und neuer.
  * Verwende **Python 3.11 32-bit** nur zum Paketieren von Abhängigkeiten für ältere unterstützte NVDA-Versionen.
* **uv** für die festgelegte Build- und Lint-Toolchain.

  ```
  uv sync
  uv run pre-commit run --all-files
  uv run scons
  uv run scons pot
  ```

  SCons 4.10.1, Markdown 3.10, Ruff 0.14.10, Pyright 1.1.407 und die weiteren Build-Tools werden aus `uv.lock` installiert.

* **GNU Gettext Tools** (optional, empfohlen)

  * Unter Linux/Cygwin meist vorinstalliert.
  * Windows: `https://gnuwin32.sourceforge.net/downlinks/gettext.php` [(gnuwin32.sourceforge.net in Bing)](https://www.bing.com/search?q="https%3A%2F%2Fgnuwin32.sourceforge.net%2Fdownlinks%2Fgettext.php")

### Zusätzliche Abhängigkeiten

Installiere die Audio‑Abhängigkeiten für Sprechen mit der KI nur für lokale Entwicklung direkt in den Add-on‑Lib‑Ordner. Verwende dabei die Python-Version und Architektur, die zur getesteten NVDA-Laufzeit passen:

```
python.exe -m pip install pyaudio --target "D:/myAdd-on/Native-Speech-Generation/addon/globalPlugins/NativeSpeechGeneration/lib"
```

Pfad entsprechend anpassen.

Die Bildschirmfreigabe verwendet die bereits in NVDA verfügbare Windows-/wx-Aufnahme. **opencv-python**, **pillow** und **mss** werden nicht benötigt.

Für Release-Pakete lädt das Add-on ausschließlich das festgelegte PyAudio-0.2.14-Wheel herunter, das zur Python-ABI und Architektur der eingebetteten NVDA-Laufzeit passt (`cp311` bis `cp313`, `win32` oder `win_amd64`). Der SHA-256-Wert ist im Add-on fest hinterlegt, wird mit den PyPI-Metadaten verglichen und nach dem Download erneut geprüft. Das Google GenAI SDK und dessen transitive Abhängigkeiten werden nicht installiert. Das Wheel wird nach `addon/globalPlugins/NativeSpeechGeneration/lib` extrahiert.

## Beiträge

Beiträge, Vorschläge und Fehlerberichte sind willkommen.

* **Issues** für Bugs oder Feature‑Wünsche.
* **Pull Requests** für Code‑Beiträge.

**Kontakt**

* E-Mail: `muha.aku@gmail.com`
* GitHub: `https://github.com/MuhammadGagah` [(github.com in Bing)](https://www.bing.com/search?q="https%3A%2F%2Fgithub.com%2FMuhammadGagah")

## Übersetzung

Diese Erweiterung wurde von BFW Würzburg im Rahmen des Projektes "NVDA Nachhaltig" ins Deutsche übersetzt.
