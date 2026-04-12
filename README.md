# Meta AI Parser for ALEAPP

An ALEAPP artifact plugin for parsing forensic artifacts from the **Meta AI / Ray-Ban Meta Android companion application** (`com.facebook.stella`) and selected **Meta cloud export** files.

This repository contains the **plugin only**. It is intended to be used with the [ALEAPP](https://github.com/abrignoni/ALEAPP) framework and is **not** a standalone parser.

---

## Overview

This plugin supports forensic parsing of artifacts associated with the Meta AI Android companion application used with Ray-Ban Meta smart glasses. It is designed to assist investigators and researchers in extracting and correlating artifacts from:

- local Android application data
- application preferences and device metadata
- selected Meta cloud export HTML files

The parser produces structured ALEAPP reports for user/account information, paired devices, media timelines, linked accounts, and selected cloud-side artifacts.

---

## Supported Artifact Sources

The current plugin targets the following inputs:

### Local application artifacts
- `*/databases/StellaDatabase*`
- `*/app_light_prefs/com.facebook.stella/*`

### Cloud export artifacts
- `*/meta_ai_profile/*.html`
- `*/meta_ai_app/*.html`
- `*/facebook_view/media/*`

---

## Current Report Outputs

The plugin currently generates the following ALEAPP reports:

1. **User Profile**
2. **Paired Devices (from DB)**
3. **Media Timeline**
4. **Paired Devices (Detailed)**
5. **Linked Accounts**
6. **AI Conversations (Cloud)**
7. **Connected Devices (Cloud)**
8. **Cloud Media Library**

---

## Requirements

- Python environment compatible with ALEAPP
- A working installation of ALEAPP
- The plugin file: `meta_ai.py`

No additional third-party Python dependencies are required beyond those already used by ALEAPP.

---

## Installation

1. Clone ALEAPP:

```bash
git clone https://github.com/abrignoni/ALEAPP.git
```
2. Copy meta_ai.py into ALEAPP’s artifact directory:
```bash
cp meta_ai.py ALEAPP/scripts/artifacts/
```
3. Run ALEAPP as usual on your extracted data source.

---

## Usage
This parser is intended for use on:
- Android filesystem extractions containing the Meta AI companion application sandbox
- Meta cloud export files matching the supported artifact paths listed above

A typical ALEAPP workflow is:
```bash
python aleapp.py -i /path/to/input -o /path/to/output
```
The exact command may vary depending on your ALEAPP setup and version.

---

## Notes and Limitations
- This repository contains the plugin only and depends on ALEAPP for execution.
- The parser was developed and tested against artifact structures available during this research project.
- Some cloud HTML parsing logic depends on the format of Meta export files and may require updates if export formats change.
- Some preference files are parsed heuristically from non-XML or binary content.
- The parser is designed to support forensic review and triage; users should validate important findings against underlying source artifacts during casework.
