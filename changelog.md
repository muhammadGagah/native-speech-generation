# Changelog

## Version 1.8.3

- Compatibility: Tested with NVDA 2026.3 while retaining NVDA 2024.1 as the minimum supported version.
- Voice Library fixes: Voice Replication now identifies the add-on to Google like every other request, creating a voice no longer extends the age of a cached catalog, and catalog responses are size-limited.
- Generation dialog fixes: Gemini 3.8 request errors now show a translated message and return focus to the voice selector instead of an internal error code. Closing the dialog while a Voice Library form or file browser is open now closes them in order.
- Translations: Updated the Indonesian translation for all new features.

### Native Speech Generation, stages 2–4

- Added Voice Remix: create a new stored voice from the selected prebuilt, catalog, designed, or remixed voice by describing relative changes. The original voice is unchanged, the name is optional, replicated voices are excluded, and requests use Gemini 3.8 Flash TTS without automatic retries.

- Grouped Voice Design and Voice Replication under New voice, with descriptive native buttons and a shared paid-tier notice. Cancel returns focus to New voice without making an API request.

- Added Voice Replication with a paid-tier notice, WAV reference and consent uploads, Indonesian/English consent statements, local audio validation, and Google's consent verification. Creation is explicit, never automatically retried, and stored voices appear in Voice Library for manual preview or selection.

- Added a Language filter beside Voice type, combining catalog language tags with search and type filters while preserving the selected filter across refreshes.
- Added a paid-tier billing requirement notice to the Voice Design window.
- Added Voice Design: create a stored custom voice from a description using the selected Gemini 3.8 TTS model. Includes an accessible form, explicit API usage notice, duplicate-request prevention, and recovery guidance when creation cannot be confirmed.
- Added Gender, Pitch, Persona, and Use case filters to Voice Library, plus corresponding details and searchable metadata. Existing caches are refreshed to load the new fields without losing saved voice selections.
- Fixed sample lookup for the extended catalog IDs (for example en-us-fola and en-us-rami), while preserving original built-in voice samples and manual preview generation.
- Voice Library Space/Enter plays an existing sample or announces that it is unavailable, without automatic generation. Generate preview explicitly uses API quota and editable preview text, with replay caching and cancellation guards. Renamed the narrator library button to View voice library. Added 40 verified recordings alongside the 30 original voices.
- Added a Voice Library for Gemini 3.8 TTS with search, voice-type filters, readable metadata, and paginated catalog loading.
- Added sample playback with Stop and cleanup when the dialog closes.
- Persisted narrator and speaker selections by stable voice ID, separately for each API key, with a 24-hour catalog cache and manual refresh.
- Preserved selections on failed refreshes and Cancel, and guarded delayed callbacks and keyboard focus during filtering and playback.
- Quick Speak and Talk With AI retain their existing behavior. Deleting custom voices is deferred to a later stage.

### Native Speech Generation, stage 1

- Added Gemini 3.8 Flash-Lite TTS as the default in the generation dialog and Gemini 3.8 Flash TTS as an additional choice.
- Separated delivery instructions from the transcript using speech metadata, with explicit speaker metadata for every dialogue turn.
- Added preflight checks and Script Help for two-speaker scripts. Validation preserves the draft and returns focus to the field requiring correction.
- Requested WAV output explicitly and preserved its existing header. Gemini 3.8 errors no longer retry with a legacy prompt format.
- Preserved older TTS request behavior, Quick Speak, and Talk With AI.

### Gemini 3.8 Live, Talk With AI, and Live API

- Audit fixes: Preserved keyboard focus during device loading and delayed disconnect cleanup, refreshed status after reconnect, ignored status callbacks from replaced connections, and preserved legacy thinking preferences across reopening the dialog.

- Quick Speak: Added Gemini 3.8 Live as the recommended model and default for new configurations, without a thinking parameter. Existing model selections and thinking behavior are preserved.
- Talk With AI: Added Gemini 3.8 Live and Gemini 3.8 Live Extended Thinking, with saved model and thinking preferences. Thinking controls are hidden for 3.8 Live, limited to Low/Medium/High for Extended Thinking, and unchanged for the previous model.
- Talk With AI: Tracks background reasoning status while continuing to receive audio after turn completion.
- Live API: Preserved partial WebSocket frames and fragmented messages across timeouts to prevent stream corruption.
- Live API: Preserved server error codes and statuses so permanent configuration errors stop reconnect attempts.
- Packaging: Included the license and current release notes in the add-on package.
