# Native Speech Generation for NVDA

**Author:** Muhammad Gagah [muha.aku@gmail.com](mailto:muha.aku@gmail.com)

Native Speech Generation is an NVDA add-on that integrates **Google Gemini AI** to generate high-quality, natural-sounding speech directly within NVDA.
It provides a clean, fully accessible interface for converting text into audio, supporting both **single-speaker narration** and **dynamic multi-speaker dialogues**.

This add-on is designed for smooth workflows, accessibility-first interaction, and flexible voice control suitable for narration, dialogue, and audio content production.

---

## Features

### High-Quality Speech Generation

* Choose between:

  * **Gemini Flash-Lite 3.8 TTS** Default for the generation dialog; fast speech generation for everyday reading and narration.
  * **Gemini Flash 3.8 TTS** Expressive speech generation for narration, acting, and multi-speaker dialogue.
  * **Gemini Flash 3.1 Preview** Powerful, low-latency speech generation, very good for short audio.
  * **Gemini Flash 2.5** Standard quality, fast generation, low latency.
  * **Gemini Pro 2.5** Premium, more realistic voices (paid model).

### Single & Multi-Speaker Modes

* **Single-speaker narration** for standard text-to-speech.
* **Multi-speaker (2 speakers)** mode for dialogues with distinct voices.

### Advanced Voice Control

* **Speaker Naming**
  Assign custom names (e.g., *John*, *Mary*) in multi-speaker mode.
  With Gemini 3.8, the add-on maps each labeled script line to the selected speaker and voice before sending it.
* **Style Instructions**
  Provide prompts such as *“Speak in a cheerful tone”* or *“Narrate calmly”* to guide delivery.
  Gemini 3.8 sends these instructions separately from the spoken text. In multi-speaker mode they apply to both speakers.
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
* Gemini 3.8 Live is the recommended default for new Quick Speak configurations and sends no thinking parameter. Existing saved model selections are preserved. Gemini API quotas and Live session limits still apply. It is not an unlimited service.
* Available Quick Speak models are Gemini 3.8 Live, Gemini 3.1 Flash Live Preview, Gemini 2.5 Flash Native Audio, Gemini 3.1 Flash TTS Preview, Gemini 2.5 Flash TTS Preview, and Gemini 2.5 Pro TTS Preview. The Pro model needs a paid API plan.
* Gemini 3.1 Flash Live Preview retains its existing high thinking setting; other previous models keep their existing behavior.
* Press either Quick Speak command again to stop the current request or playback.

### Talk With AI (Live Conversation)

* **Real-time Voice Chat**: Have a natural, low-latency spoken conversation with Gemini.
* **Grounding with Google Search**: Enable the AI to access real-time information from the web during your chat.
* **Interruptible**: You can interrupt the AI at any time by speaking or pressing "Stop Conversation".
* **Customizable**: Uses your selected voice and style instructions.
* **Conversation Model**: Choose Gemini 3.8 Live, Gemini 3.8 Live Extended Thinking, or the existing Gemini 3.1 Flash Live Preview. Model and thinking preferences are saved when the dialog closes.
* **Thinking Level Control**: Gemini 3.8 Live hides the thinking control and sends no thinking parameter. Extended Thinking offers `Low`, `Medium`, and `High`. Gemini 3.1 Flash Live Preview retains `No Thinking` (`minimal`), `Low`, `Medium`, and `High`.
* **Background Reasoning**: Extended Thinking continues receiving responses after an audio turn completes and displays the model processing status without interrupting speech.
* **Reconnect Continuity**: Recent conversation context is restored automatically after a reconnect, without a separate memory toggle.
* **More Stable Streaming**: Improved reconnection behavior (backoff + retry) and adaptive audio buffering for better resilience on unstable networks.
* **Optional Screen Sharing**: Enable **Share screen with AI** to send a periodic view of the primary display. It is off by default and stops immediately with the conversation or dialog.

---

## Requirements

* NVDA 2024.1 or newer, tested through NVDA 2026.3.
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

  * Flash-Lite 3.8 TTS (default)
  * Flash 3.8 TTS
  * Flash 3.1 Preview
  * Flash 2.5
  * Pro 2.5 (High Quality, need paid API)
* **Speaker Mode**

  * Single-speaker
  * Multi-speaker (2)

---

## Generating Speech

### Gemini 3.8 TTS

The generation dialog includes Flash-Lite 3.8 TTS and Flash 3.8 TTS. This update does not change Quick Speak or Talk With AI.

For one speaker, enter only the text to be spoken in **Text to convert**. Put delivery directions in **Style instructions**.

For two speakers, enter two distinct names and choose their voices. Write one turn per line using the exact name followed by a colon:

```text
Andi: Selamat pagi.
Budi: Pagi juga. Kita mulai pukul 10:30.
Andi: <laugh> Baik, sampai nanti!
```

Every nonblank line must include a speaker label and spoken text. Blank lines are ignored. Names cannot contain colons or line breaks, and names differing only in capitalization are not allowed. Additional colons inside the spoken text are preserved. **Script Help** opens instructions with examples using your current names.

The add-on checks the script before sending it. If there is an error, dismiss the message to return to the field that needs correction; your draft stays intact. Successful Gemini 3.8 responses are saved as WAV without adding a second audio header.

### Voice Library

With a Gemini 3.8 TTS model selected, open **View voice library**, **Speaker 1 voice library**, or **Speaker 2 voice library**. The library loads the voices available to your API key, including existing designed and replicated voices.

1. Search by name, language, accent, or description, and optionally combine **Voice type**, **Language**, **Gender**, **Pitch**, **Persona**, and **Use case** filters. Language options come from the catalog (for example, `id-ID` or `en-US`); **All languages** clears this filter and **Unspecified** shows entries without language metadata. The language filter matches the catalog tag, not every language a voice can speak. The other filters use metadata returned by Google, with **All** and **Unspecified** options. Persona approximates AI Studio's Style filter; Use case corresponds to the API context. Filters use exact case-insensitive matches and combine with AND. These filters select existing voices; they do not change how a voice speaks.
2. Select a voice in **Available voices**. Read **Voice details** to distinguish voices with identical names.
3. Press **Space** or **Enter** on the selected voice to play its existing sample. If unavailable, a message is announced; speech is never generated automatically. To generate audio explicitly, edit **Preview text** (up to 300 characters) and activate **Generate preview** (Alt+G). This uses the selected Gemini 3.8 TTS model and API quota, for any selected voice.
4. **Stop sample** stops playback or ignores a pending response. A generation request already sent to Google may still consume quota. Repeated activation while loading or generating does not submit another request.
5. Activate **Use selected voice** to apply it to that narrator or speaker. **Cancel** leaves your choice unchanged.

The checked library option shows which voice speech generation will use. Uncheck it, or change the original voice selector, to return to a built-in voice. Talk With AI continues to use its original built-in selector; library choices do not affect Quick Speak.

Existing samples cover 30 original built-in voices, 40 additional voices verified against AI Studio on September 28, 2026 (including Fola and Rami), and designed voices whose details include a sample. Voices without recordings, including regional prebuilt voices such as ar-eg-commercial-9 and replicated voices, report that the sample is unavailable. Generate preview remains a separate, explicit action. The last successful generated preview is kept in memory until the library closes; replaying it with the same voice, model, and text does not generate it again. Download errors do not silently trigger generation. Preview availability still depends on the API key, model access, quota, and connection.

Older catalogs are automatically refreshed once to load the new metadata; saved voice selections are preserved. Catalogs are cached for 24 hours and can be updated with **Refresh**. If refreshing fails, the previous results remain available. Selections use stable voice IDs and are saved separately for each API key in the NVDA configuration directory. API keys are not written into these cache files. If NVDA disallows writing configuration, choices last only for the session and sample playback is unavailable.

### Voice Design

Voice Design requires a Gemini API key from a project with billing enabled (paid tier). Free-tier API keys cannot create voices.

Open **View voice library**, then **New voice** (Alt+W), then **Voice Design** (Alt+D). Each creation method has a short description in the chooser. Enter a name (up to 100 characters) and a description (up to 2000 characters) of the voice's age, tone, accent, and delivery. Language tag and gender are optional metadata. Include important vocal characteristics in the description itself.

Activate **Create voice** to send one request using your selected Gemini 3.8 TTS model. This uses API quota and immediately stores the voice in your Google project. **Cancel** in the form makes no request. Google documents a limit of 200 stored custom voices per project and a one-year lifetime; closing the library does not delete a voice.

When creation succeeds, the library clears its filters and selects the new voice. Press Space/Enter on it to fetch its existing sample, use **Generate preview** for a custom test sentence, or activate **Use selected voice** to apply it to the narrator or speaker. Creation does not automatically start playback or change the main dialog's voice selection.

Closing the library during creation only closes the local view; the server request may still finish and consume quota. If creation cannot be confirmed, use **Refresh** before retrying to avoid creating a duplicate. A successful voice remains in Google even if the local cache could not be saved.

### Voice Remix

Voice Remix creates a new voice by describing changes to an existing one. The original voice is never modified. Like Voice Design, it requires a Gemini API key from a project with billing enabled (paid tier).

In **View voice library**, select a prebuilt, catalog, designed, or previously remixed voice, then activate **Remix selected voice** (Alt+M). The button is unavailable for replicated voices, which Google does not list as remix sources. Describe one or two changes at a time, such as age, pitch, energy, pacing, tone, or accent (up to 2000 characters). A name for the new voice is optional; without one, the library shows the new voice ID.

Activate **Create voice** to send one request. Remixes are always created with Gemini 3.8 Flash TTS, and the result works with both Gemini 3.8 TTS models. The request uses API quota and stores the new voice in your Google project, counting toward the same 200-voice limit as designed and replicated voices. Remixed voices appear as **Designed**, have a downloadable sample, and can themselves be remixed again. **Cancel** makes no request, and the same duplicate-prevention and Refresh guidance as Voice Design applies.

See Google's [Voice Remixing guide](https://aistudio.google.com/docs/voice-remixing) for details.

### Voice Replication

Open **View voice library**, then **New voice** (Alt+W), then **Voice Replication** (Alt+R). This feature requires a Gemini API key from a project with billing enabled (paid tier); free-tier keys cannot create voices.

Enter a voice name and choose two real recordings from the same adult speaker: clean reference speech and the speaker's recorded consent. The form offers the exact consent statement in Indonesian or English in a read-only, selectable field. The statement language only changes the instructions; it does not set the voice's synthesis language. Google verifies the recordings when creating the voice.

This first version accepts existing **24 kHz, mono, 16-bit PCM WAV** files. Reference speech must be **10–30 seconds**; the add-on limits the consent clip to **60 seconds**. These format and duration checks run before upload. Recording directly from the microphone and automatic format conversion are not included yet.

Select both files, confirm the speaker's recorded consent, then activate **Create voice**. Both recordings are sent to Google, the request uses API quota, and the resulting voice is stored in your Google project. Canceling the form uploads nothing. The add-on caches only catalog metadata, not a copy of the recordings. Your original local files are unchanged.

After creation, use **Generate preview** to hear the voice with an explicit API request, or **Use selected voice** to apply it. Replicated voices have no downloadable sample. Closing the library does not cancel a submitted request. If creation cannot be confirmed, refresh the library before trying again. Custom voice deletion remains planned for a later stage.

See Google's [Voice Replication guide](https://ai.google.dev/gemini-api/docs/voice-replication) for recording and consent requirements.

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

  SCons 4.10.1, Markdown 3.10, Ruff 0.17.4, Pyright 1.1.407, and the other build tools are installed from `uv.lock`.
* **Unit tests** use only the Python standard library and must run on Windows, because the add-on uses Windows-only modules such as `winsound`. From the repository root:

  ```
  py -3.13 -m unittest discover -s tests
  py -3.11-32 -m unittest discover -s tests
  ```

  GitHub Actions runs the same suite on Windows with 32-bit Python 3.11 (NVDA 2024.1–2025.x) and 64-bit Python 3.13 (NVDA 2026.1 and newer). A release is published only when both pass.
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
