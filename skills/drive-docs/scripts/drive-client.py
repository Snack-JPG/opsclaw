#!/usr/bin/env python3
"""Google Drive wrapper built on top of gws."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_gws(command: list[str]) -> Any:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown gws error"
        raise RuntimeError(f"{' '.join(command)} failed: {stderr}")
    stdout = completed.stdout.strip()
    if not stdout:
        return {}
    return json.loads(stdout)


def gws_drive(resource: str, method: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, upload: Path | None = None, output: Path | None = None) -> Any:
    command = ["gws", "drive", resource, method]
    if params is not None:
        command.extend(["--params", json.dumps(params)])
    if body is not None:
        command.extend(["--json", json.dumps(body)])
    if upload is not None:
        command.extend(["--upload", str(upload)])
    if output is not None:
        command.extend(["--output", str(output)])
    return run_gws(command)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search Drive files by query.")
    search_parser.add_argument("--query", required=True, help="Drive query terms.")
    search_parser.add_argument("--config", type=Path, help="Optional drive-config.json for default page size.")
    search_parser.add_argument("--page-size", type=int, help="Override page size.")

    list_parser = subparsers.add_parser("list", help="List files in a folder.")
    list_parser.add_argument("--folder-id", required=True, help="Drive folder ID.")
    list_parser.add_argument("--page-size", type=int, default=25, help="Page size.")

    download_parser = subparsers.add_parser("download", help="Download a Drive file.")
    download_parser.add_argument("--file-id", required=True, help="Drive file ID.")
    download_parser.add_argument("--output", type=Path, required=True, help="Output path.")

    upload_parser = subparsers.add_parser("upload", help="Upload a file to Drive.")
    upload_parser.add_argument("--path", type=Path, required=True, help="Local file path.")
    upload_parser.add_argument("--folder-id", help="Parent Drive folder ID.")
    upload_parser.add_argument("--name", help="Override uploaded file name.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.command == "search":
            page_size = args.page_size
            if page_size is None and args.config:
                page_size = int(load_json(args.config).get("defaults", {}).get("defaultPageSize", 25))
            q = f"name contains '{args.query}' or fullText contains '{args.query}'"
            result = gws_drive("files", "list", params={"q": q, "pageSize": page_size or 25, "fields": "files(id,name,mimeType,modifiedTime,parents,webViewLink)"})
        elif args.command == "list":
            q = f"'{args.folder_id}' in parents and trashed=false"
            result = gws_drive("files", "list", params={"q": q, "pageSize": args.page_size, "fields": "files(id,name,mimeType,modifiedTime,webViewLink)"})
        elif args.command == "download":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            result = gws_drive("files", "get", params={"fileId": args.file_id, "alt": "media"}, output=args.output)
            result = {"ok": True, "fileId": args.file_id, "output": str(args.output), "response": result}
        elif args.command == "upload":
            metadata: dict[str, Any] = {"name": args.name or args.path.name}
            if args.folder_id:
                metadata["parents"] = [args.folder_id]
            result = gws_drive("files", "create", body=metadata, upload=args.path)
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc), "command": args.command}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    json.dump({"ok": True, "command": args.command, "result": result}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
