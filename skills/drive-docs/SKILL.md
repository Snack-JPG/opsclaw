---
name: drive_docs
description: Google Drive and Google Docs operations for OpsClaw through the Google Workspace CLI (`gws`): search folders, list files, upload/download documents, create docs, read doc structure, and apply text updates.
---

# Drive Docs Skill

Use this skill whenever the user asks to search Drive, inspect shared folders, download or upload files, create or update Google Docs, or maintain a Drive-based document workspace for OpsClaw.

## Load Order
1. Read `workspace/SOUL.md`, `workspace/USER.md`, and `workspace/ops-state.json` when document work needs owner context.
2. Read `config/drive-config.json` to see which folders are monitored by default.
3. Use the bundled scripts for deterministic operations:
   - `scripts/drive-client.py`
   - `scripts/docs-client.py`

## Default Workflow
1. Confirm `gws` is installed and authenticated with `gws auth status`.
2. Use `scripts/drive-client.py` for Drive file search, listing, upload, and download.
3. Use `scripts/docs-client.py` for Doc creation, reading, and batch text updates.
4. Treat file writes, uploads, and document edits as approval-gated when they affect external or shared documents.

## Typical Commands
- `Find the latest proposal doc`
  - Run `scripts/drive-client.py search --query "<terms>"`.
- `Show files in the client folder`
  - Run `scripts/drive-client.py list --folder-id <id>`.
- `Upload this file to Drive`
  - Run `scripts/drive-client.py upload --path <local-path> --folder-id <id>`.
- `Download the meeting brief`
  - Run `scripts/drive-client.py download --file-id <id> --output <path>`.
- `Create a new Google Doc`
  - Run `scripts/docs-client.py create --title "<title>"`.
- `Append notes to the doc`
  - Read the doc with `scripts/docs-client.py get`, then update it with `scripts/docs-client.py replace-text` or `append-text`.

## Reliability Notes
- Use `gws drive files list|get|create|update` for Drive operations.
- Use `gws docs documents create|get|batchUpdate` for Docs operations.
- Prefer structured JSON outputs from the scripts and keep raw file contents out of logs unless the user asked for them.
- If a monitored folder is missing from config, ask before picking an alternative folder.
