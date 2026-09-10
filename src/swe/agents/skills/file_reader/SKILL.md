---
name: file_reader
description: "Read and summarize text-based files. Prefer read_file for text formats; read_file also extracts plain text from Word (.docx/.docm), Excel (.xlsx/.xlsm) and PowerPoint (.pptx/.pptm) documents automatically, and from legacy .doc when antiword is installed. PDF, images, audio, video and archives are out of scope; use execute_shell_command or dedicated skills for those."
metadata:
  {
    "builtin_skill_version": "1.0",
    "swe":
      {
        "emoji": "📄",
        "requires": {}
      }
  }
---
# File Reader Toolbox

Use this skill when the user asks to read or summarize local text-based files. PDFs, Office documents, images, audio, and video are out of scope for this skill and should be handled by their dedicated skills/tools.

## Quick Type Check

Use a type probe before reading:

```bash
file -b --mime-type "/path/to/file"
```

If the file is large, avoid dumping the whole content; extract a small, relevant portion and summarize.

## Text-Based Files (use read_file)

Preferred for: `.txt`, `.md`, `.json`, `.yaml/.yml`, `.csv/.tsv`, `.log`, `.sql`, `ini`, `toml`, `py`, `js`, `html`, `xml` source code.

Steps:

1. Use `read_file` to fetch content.
2. Summarize key sections or show the relevant slice requested by the user.
3. For JSON/YAML, list top-level keys and important fields.
4. For CSV/TSV, show header + first few rows, then summarize columns.

## Office Documents (use read_file)

`read_file` auto-detects binary Office formats by file signature and returns their text content:

| Format | Notes |
|--------|-------|
| `.docx` / `.docm` | Paragraphs and tables extracted from `word/document.xml` |
| `.xlsx` / `.xlsm` | One line per non-empty row, `=== Sheet: <name> ===` headers |
| `.pptx` / `.pptm` | Text frames and tables per slide, `=== Slide N ===` headers |
| `.doc` (legacy) | Requires `antiword` installed; otherwise convert to `.docx` first |

Not supported by `read_file` (clear error returned): legacy `.xls` / `.ppt`, PDF, and generic ZIP/ODF archives. Use the `xlsx`/`docx` skills or `execute_shell_command` (pandoc, LibreOffice, pandas) for those.

## Large Logs

If the file is huge, use a tail window:

```bash
tail -n 200 "/path/to/file.log"
```

Summarize the last errors/warnings and notable patterns.

## Out of Scope

Do not handle the following in this skill (they are covered by other skills):

- PDF
- Images
- Audio/Video
- Archives (zip/tar/gz) and OpenDocument (odt/ods/odp)
- Editing or creating Office files (use the `docx` / `xlsx` skills)

## Safety and Behavior

- Never execute untrusted files.
- Prefer reading the smallest portion necessary.
- If a tool is missing, explain the limitation and ask the user for an alternate format.
