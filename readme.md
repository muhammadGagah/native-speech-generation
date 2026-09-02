# Native Speech Generation for NVDA

**Author:** Muhammad Gagah [muha.aku@gmail.com](mailto:muha.aku@gmail.com)

Native Speech Generation is an NVDA add-on that integrates **Google Gemini AI** to generate high-quality, natural-sounding speech directly within NVDA.
It provides a clean, fully accessible interface for converting text into audio, supporting both **single-speaker narration** and **dynamic multi-speaker dialogues**.

This add-on is designed for smooth workflows, accessibility-first interaction, and flexible voice control suitable for narration, dialogue, and audio content production.

---

## Features

### High-Quality Speech Generation

* Choose between:

  * **Gemini Flash 3.1 Preview** Powerful, low-latency speech generation, very good for short audio.
  * **Gemini Flash 2.5** Standard quality, fast generation, low latency.
  * **Gemini Pro 2.5** Premium, more realistic voices (paid model).

### Single & Multi-Speaker Modes

* **Single-speaker narration** for standard text-to-speech.
* **Multi-speaker (2 speakers)** mode for dialogues with distinct voices.

### Advanced Voice Control

* **Speaker Naming**
  Assign custom names (e.g., *John*, *Mary*) in multi-speaker mode.
  The AI automatically maps voices based on speaker names in the script.
* **Style Instructions**
  Provide prompts such as *“Speak in a cheerful tone”* or *“Narrate calmly”* to guide delivery.
* **Temperature Control**
  Adjust output variation and creativity:

  * Lower values → more stable and predictable speech.
  * Higher values → more expressive and varied speech.

### Accessible & Clean Interface

* Fully accessible with screen readers.
* Advanced options are placed in a collapsible panel to keep the main dialog simple and focused.

### Seamless Workflow

* Audio plays automatically after generation.
* Generated audio can be replayed or saved as a high-quality `.wav` file.
* Designed for minimal friction during repeated generation and playback.

### Smart Voice Loading & Caching

* The supported Gemini voice list is built into the add-on, so opening the dialog does not require a separate voice-list request.

### Quick Speak

* Speak selected text immediately with **NVDA+Alt+E**.
* Speak plain text from the clipboard with **NVDA+Alt+Shift+E**.
* Audio plays internally through NVDA's configured output device, so focus stays in Word, Chrome, or the current application.
* Quick Speak has separate model, voice, volume, and pronunciation/style settings in NVDA Settings.
* Quick Speak volume ranges from 0 (silent) to 100 (full volume) and is saved between NVDA restarts.
* The selected or clipboard text is sent to Google Gemini to generate the requested audio.
* Gemini 3.1 Flash Live Preview is the recommended default for low latency. Gemini API quotas and Live session limits still apply. It is not an unlimited service.
* Available Quick Speak models are Gemini 3.1 Flash Live Preview, Gemini 2.5 Flash Native Audio, Gemini 3.1 Flash TTS Preview, Gemini 2.5 Flash TTS Preview, and Gemini 2.5 Pro TTS Preview. The Pro model needs a paid API plan.
* Press either Quick Speak command again to stop the current request or playback.

### Talk With AI (Live Conversation)

* **Real-time Voice Chat**: Have a natural, low-latency spoken conversation with Gemini.
* **Grounding with Google Search**: Enable the AI to access real-time information from the web during your chat.
* **Interruptible**: You can interrupt the AI at any time by speaking or pressing "Stop Conversation".
* **Customizable**: Uses your selected voice and style instructions.
* **Thinking Level Control**: Choose `No Thinking`, `Low`, `Medium`, or `High` depending on the reasoning depth you want.
* **Reconnect Continuity**: Recent conversation context is restored automatically after a reconnect, without a separate memory toggle.
* **More Stable Streaming**: Improved reconnection behavior (backoff + retry) and adaptive audio buffering for better resilience on unstable networks.
* **Optional Screen Sharing**: Enable **Share screen with AI** to send a periodic view of the primary display. It is off by default and stops immediately with the conversation or dialog.

---

## Requirements

* NVDA 2024.1 or newer, tested through NVDA 2026.2.
* Active internet connection.
* A valid **Google Gemini API Key**.

---

## Installation

1. Download the latest add-on package from the
   **Releases page:**
   [https://github.com/MuhammadGagah/native-speech-generation/releases](https://github.com/MuhammadGagah/native-speech-generation/releases)
2. Install it like any standard NVDA add-on.
3. Restart NVDA when prompted.

---

## API Key Setup (Required)

1. Create an API key from **Google AI Studio**:
   [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Open NVDA and go to:
   **NVDA Menu → Tools → Native Speech Generation**
3. Click **“API Key Settings”**.
4. This opens NVDA Settings directly in the *Native Speech Generation* category.
5. Paste your **Gemini API Key** into the *GEMINI API Key* field.
6. Click **OK** to save.

Saved keys are stored securely using **Windows DPAPI**, so the encrypted value cannot be
decrypted on a different Windows machine or user account.

For advanced deployments, you can also provide the key through the
**`GEMINI_API_KEY`** environment variable. The add-on will use it automatically when
no stored key is available.

---

## How to Use

Open the dialog using:

* **NVDA+Control+Shift+G**, or
* **NVDA Menu → Tools → Native Speech Generation**

### Main Interface Elements

* **Text to convert**
  Enter or paste the text you want to convert to speech.
* **Style instructions (optional)**
  Provide guidance for tone, emotion, or delivery.
* **Select Model**

  * Flash 3.1 Preview
  * Flash 2.5
  * Pro 2.5 (High Quality, need paid API)
* **Speaker Mode**

  * Single-speaker
  * Multi-speaker (2)

---

## Generating Speech

### Quick Speak for Selected or Clipboard Text

1. Open **NVDA Settings -> Native Speech Generation** and choose the Quick Speak model, voice, volume, and optional pronunciation/style instructions.
2. Select text in the current application and press **NVDA+Alt+E**, or copy text and press **NVDA+Alt+Shift+E**.
3. The generated speech plays without opening a dialog or changing application focus.
4. Press either Quick Speak command again to stop.

Routine generation and completion messages are intentionally silent so they do not compete with the generated pronunciation. Actionable errors are still announced.

### Single-Speaker Mode

1. Select **Single-speaker**.
2. Choose a voice from the *Select Voice* dropdown.
3. Enter your text.
4. Optionally add style instructions.
5. Click **Generate Speech**.
6. The audio will play automatically after generation.

---

### Multi-Speaker Mode

1. Select **Multi-speaker (2)**.
2. For each speaker:

   * Enter a unique **Speaker Name**.
   * Select a distinct **Voice**.
3. Format the text so each line starts with the speaker name followed by a colon.

**Example:**

```
Alice: Hi Bob, how are you today?
Bob: I'm doing great, Alice! The weather is fantastic.
```

4. Click **Generate Speech**.
   Voices will be assigned automatically based on the speaker names.

---

## Talk With AI (Live Mode)

Experience a natural, two-way voice conversation with Gemini.

1. Configure your desired **Voice** and **Style Instructions** in the main dialog.
   *(Note: Talk With AI currently supports Single-speaker mode only)*
2. Click **Talk With AI**.
3. In the new window:
   * **Start Conversation**: Begins the session. Speak into your microphone.
   * **Stop Conversation**: Ends the session.
   * **Grounding with Google Search**: Check this box to allow Gemini to search the web for answers (e.g., current news, weather).
     * *Note: This checkbox is hidden while a conversation is active. Stop the conversation to change it.*
   * **Thinking level**: Choose `No Thinking`, `Low`, `Medium`, or `High`.
   * **Share screen with AI**: Optional and off by default. Enable it only when you want the assistant to receive periodic screen frames.
   * **Microphone Toggle**: Mute/Unmute your microphone.
   * **Volume**: Adjust the AI's playback volume. The volume and selected input and output devices are saved when the dialog closes.

---

## Advanced Settings

* Enable **Advanced Settings (Temperature)** to show the slider.
* **Temperature Range**:

  * `0.0` → Most deterministic and stable.
  * `1.0` → Default balance.
  * `2.0` → Most creative and varied.

---

## Buttons Overview

* **Generate Speech** - Start speech generation.
* **Play** - Replay the last generated audio.
* **Talk With AI** - Open the real-time voice conversation interface.
* **Save Audio** - Save the last audio as a `.wav` file.
* **API Key Settings** - Open the add-on configuration in NVDA Settings.
* **View voices in AI Studio** - Opens Google AI Studio in a browser.
* **Close** - Close the dialog (or press `Escape`).

---

## Input Gestures

Customizable via:
**NVDA Menu → Preferences → Input Gestures → Native Speech Generation**

Default gestures:

* **NVDA+Control+Shift+G** – Open Native Speech Generation dialog.
* **NVDA+Alt+E** - Speak selected text with Quick Speak, or stop Quick Speak.
* **NVDA+Alt+Shift+E** - Speak clipboard text with Quick Speak, or stop Quick Speak.

All three commands can be changed or removed in NVDA's Input Gestures dialog.

---

## Development & Contribution Guide

If you want to develop or modify this add-on, follow the steps below.

### Environment Setup

* **Python matching your target NVDA runtime**
  * Use **Python 3.13 64-bit** when testing or packaging dependencies for NVDA 2026.1 and newer.
  * Use **Python 3.11 32-bit** only when packaging dependencies for older supported NVDA builds.
* **uv** for the pinned build and lint toolchain.

  ```
  uv sync
  uv run pre-commit run --all-files
  uv run scons
  uv run scons pot
  ```

  SCons 4.10.1, Markdown 3.10, Ruff 0.14.10, Pyright 1.1.407, and the other build tools are installed from `uv.lock`.
* **GNU Gettext Tools** (optional, recommended for localization)

  * Usually preinstalled on Linux/Cygwin.
  * Windows: [https://gnuwin32.sourceforge.net/downlinks/gettext.php](https://gnuwin32.sourceforge.net/downlinks/gettext.php)
### Additional Dependencies

For local development only, install the audio-only Talk With AI dependencies directly into the add-on library path using the Python version and architecture that match the NVDA runtime you are testing:

```
python.exe -m pip install pyaudio --target "D:/myAdd-on/Native-Speech-Generation/addon/globalPlugins/NativeSpeechGeneration/lib"
```

Adjust the path according to your local add-on source directory.

Screen sharing uses Windows/wx capture already available in NVDA, so you do not need `opencv-python`, `pillow`, or `mss`.

For release packages, the add-on downloads only the pinned PyAudio 0.2.14 wheel that matches NVDA's embedded Python ABI and architecture (`cp311` through `cp313`, `win32` or `win_amd64`). The wheel's SHA-256 is pinned in the add-on, checked against PyPI metadata, and verified again after download. No Google GenAI SDK or transitive SDK dependencies are installed. The wheel is extracted to `addon/globalPlugins/NativeSpeechGeneration/lib`.

---

## Contributing

Contributions, suggestions, and bug reports are very welcome.

* Open an **Issue** for bugs or feature requests.
* Submit a **Pull Request** for code contributions.

**Contact**

* Email: `muha.aku@gmail.com`
* GitHub: [https://github.com/MuhammadGagah](https://github.com/MuhammadGagah)
