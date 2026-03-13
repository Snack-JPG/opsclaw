#!/usr/bin/env python3
"""Google Docs wrapper built on top of gws."""

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


def gws_docs(method: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
    command = ["gws", "docs", "documents", method]
    if params is not None:
        command.extend(["--params", json.dumps(params)])
    if body is not None:
        command.extend(["--json", json.dumps(body)])
    return run_gws(command)


def document_text(doc: dict[str, Any]) -> str:
    fragments: list[str] = []
    body = doc.get("body", {})
    for item in body.get("content", []) or []:
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []) or []:
            text_run = element.get("textRun") or {}
            content = text_run.get("content")
            if content:
                fragments.append(content)
    return "".join(fragments).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new Google Doc.")
    create_parser.add_argument("--title", required=True, help="Document title.")

    get_parser = subparsers.add_parser("get", help="Read a Google Doc.")
    get_parser.add_argument("--document-id", required=True, help="Google Doc ID.")
    get_parser.add_argument("--text-only", action="store_true", help="Return extracted plain text.")

    replace_parser = subparsers.add_parser("replace-text", help="Replace text throughout a document.")
    replace_parser.add_argument("--document-id", required=True, help="Google Doc ID.")
    replace_parser.add_argument("--search", required=True, help="Text to replace.")
    replace_parser.add_argument("--replace", required=True, help="Replacement text.")

    append_parser = subparsers.add_parser("append-text", help="Append text to the end of a document.")
    append_parser.add_argument("--document-id", required=True, help="Google Doc ID.")
    append_parser.add_argument("--text", required=True, help="Text to append.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.command == "create":
            result = gws_docs("create", body={"title": args.title})
        elif args.command == "get":
            result = gws_docs("get", params={"documentId": args.document_id})
            if args.text_only:
                result = {"documentId": args.document_id, "text": document_text(result)}
        elif args.command == "replace-text":
            result = gws_docs(
                "batchUpdate",
                params={"documentId": args.document_id},
                body={
                    "requests": [
                        {
                            "replaceAllText": {
                                "containsText": {"text": args.search, "matchCase": True},
                                "replaceText": args.replace,
                            }
                        }
                    ]
                },
            )
        elif args.command == "append-text":
            doc = gws_docs("get", params={"documentId": args.document_id})
            end_index = max(1, doc.get("body", {}).get("content", [{}])[-1].get("endIndex", 1) - 1)
            result = gws_docs(
                "batchUpdate",
                params={"documentId": args.document_id},
                body={"requests": [{"insertText": {"location": {"index": end_index}, "text": f"\n{args.text}\n"}}]},
            )
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
