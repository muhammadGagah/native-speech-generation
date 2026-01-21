**changelog v1.5.3**

- **Code Refactoring:** Huge refactoring of codebase to strictly comply with NVDA coding standards (Tabs indentation, CamelCase naming, Type Hinting).
- **Optimization:** Optimized add-on size and update process. Library updates now preserve existing files, preventing redownloading data.
- **Improved UX:** 
  - Restored Speaker/Microphone device selection in "Talk With AI".
  - "Talk With AI" button is now disabled during speech generation handling to prevent conflicts.
  - Dialogs now properly close and cancel active generation when pressing ESC.
- **Fix:** Resolved namespace conflicts with NVDA's built-in GUI module.
