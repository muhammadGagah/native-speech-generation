# Changelog

## version 1.5.4

- Stability: Restored previous dependency handling to resolve crashes (pyo3 panic) caused by aggressive module unloading.
- Localization: Fixed missing translations for Interface and Settings dialogs by ensuring all source files are included in the build process.
- Fix: Resolved "FileNotFoundError" for SSL certificates by patching `certifi` to locate the certificate file correctly within the add-on's directory.
