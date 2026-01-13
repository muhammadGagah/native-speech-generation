**changelog v1.5.2**
- Reverting the lib updator code due to SSL issues
- Now talkWithAI has a feature to change the input and output used.

**changelog v1.5.1**

- Fix issue with SSL.
- Fixing libraries that conflict with other add-ons.

**changelog v1.5**

* **New Feature:** Added "Grounding with Google Search" in Talk With AI.
  * Allows the AI to search the web for real-time information.
  * Toggle available in the Talk With AI dialog (disappears during active conversation).

**changelog v1.4**

* **New Feature: "Talk With AI" (Gemini Live):**
  * Real-time, low-latency voice conversation with Gemini.
  * Supports interruption (stop speaking to interrupt the AI).
  * Uses the selected voice and style instructions from the main dialog.
  You must reinstall the library to use the Talk with AI feature.
  
* **Improvement:** Enhanced audio handling for smoother streaming.

**changelog v1.3**

* **Code Refactoring:** Performed a comprehensive code cleanup and resolved dependency conflicts for better stability.

* **New Feature: "Reinstall Libraries":** Added a utility to reinstall/refresh the `google-genai` library, specifically designed to resolve potential runtime errors.

* **Compatibility Update:** The minimum requirement has been updated. **NVDA 2024.1** or higher is now required.

* **Localization:** Added full support for the **Russian** language.

* **Fix readme:** Rewritten so that it is easier to understand
