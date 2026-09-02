# Changelog

## version 1.8.1

- Dependency installer: Added a Windows CryptoAPI certificate-chain refresh for systems that cannot verify the PyPI certificate because a trusted issuer is missing.
- Dependency installer: Retries the original HTTPS request once after the refresh while preserving normal TLS validation and the pinned PyAudio SHA-256 check.
- Compatibility: Retains NVDA 2024.1 as the minimum supported version and remains tested with NVDA 2026.2.

Previous 1.8.0 changes are included in the release history.

- Live API: Fixed binary WebSocket JSON frames being discarded, which caused Quick Speak and Talk With AI to time out during setup.
- Live API: Added setup/response timeouts, server error and close-reason propagation, and clearer first-connection retry status.
- Talk With AI: Prioritized default audio devices, saved selected input and output devices and playback volume, flushed native playback on interruption, hardened audio shutdown, and fixed screen capture scheduling/failure handling.
- Quick Speak: Added `NVDA+Alt+E` to speak selected text without opening a dialog or moving focus, Thanks to Ivan Yatsyha for this idea.
- Quick Speak: Added `NVDA+Alt+Shift+E` to speak clipboard text. The NVDA modifier prevents the command from unnecessarily consuming a common application shortcut.
- Quick Speak: Added separate model, voice, and pronunciation/style settings, with Gemini 3.1 Flash Live Preview as the low-latency recommended default.
- Quick Speak: Added a persistent 0 to 100 playback volume setting.
- Quick Speak: Uses high thinking by default for Gemini 3.1 Flash Live Preview so pronunciation and style instructions influence Live speech more reliably. Other selectable models are unchanged.
- Quick Speak: Added in-memory playback through NVDA's configured output device, silent routine states, protected-field blocking, focus-mode selection handling, cancellation during Live connection setup, and streamlined settings without the usage/privacy help field.
- Accessibility: Added remapping-safe key-repeat suppression, stale playback protection, actionable error announcements, and focus-preserving settings validation.
- Localization: Updated German, Spanish, Indonesian, Russian, and Ukrainian translations and documentation.
- Compatibility: Tested with NVDA 2026.2 while retaining NVDA 2024.1 as the minimum supported version.

Special thanks to Mahmoodhozhabri, developer of Vision Assistant Pro, whose work inspired Native Speech Generation's migration from the Google GenAI SDK to a direct WebSocket-based API architecture. If you are interested, you can explore the project and install the add-on from the [Vision Assistant Pro GitHub repository](https://github.com/mahmoodhozhabri/VisionAssistantPro).
