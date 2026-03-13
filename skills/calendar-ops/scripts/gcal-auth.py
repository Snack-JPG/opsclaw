#!/usr/bin/env python3
"""Google Calendar OAuth2 bootstrap and token management for OpsClaw."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_logger_module() -> Any:
    """Load the shared logger module without importing the package __init__."""
    module_path = REPO_ROOT / "scripts" / "logger.py"
    spec = importlib.util.spec_from_file_location("opsclaw_shared_logger", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load logger module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCOPES = ["https://www.googleapis.com/auth/calendar"]
LOG = load_logger_module().get_logger("opsclaw.calendar.auth")


class DependencyError(RuntimeError):
    """Raised when optional Google dependencies are unavailable."""


def require_google_auth() -> tuple[Any, Any, Any]:
    """Import Google auth modules lazily and fail with an actionable message."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise DependencyError(
            "Missing Google Calendar dependencies. Install with: "
            "python3 -m pip install google-api-python-client google-auth google-auth-oauthlib"
        ) from exc
    return Request, Credentials, InstalledAppFlow


def utc_now() -> datetime:
    """Return the current UTC time without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_expiry(value: str | None) -> datetime | None:
    """Parse a Google credential expiry timestamp."""
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class TokenStatus:
    """Serializable token status."""

    exists: bool
    valid: bool
    expired: bool
    has_refresh_token: bool
    expiry: str | None
    scopes: list[str]
    token_path: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-friendly form."""
        return {
            "exists": self.exists,
            "valid": self.valid,
            "expired": self.expired,
            "hasRefreshToken": self.has_refresh_token,
            "expiry": self.expiry,
            "scopes": self.scopes,
            "tokenPath": self.token_path,
        }


def save_token(path: Path, creds: Any) -> None:
    """Persist credential JSON to disk with parent creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")


def load_token(path: Path) -> dict[str, Any]:
    """Load raw token JSON from disk."""
    if not path.exists():
        raise FileNotFoundError(f"Token file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_status(token_path: Path) -> TokenStatus:
    """Inspect token file metadata without refreshing it."""
    if not token_path.exists():
        return TokenStatus(
            exists=False,
            valid=False,
            expired=False,
            has_refresh_token=False,
            expiry=None,
            scopes=[],
            token_path=str(token_path),
        )

    token_doc = load_token(token_path)
    expiry = parse_expiry(token_doc.get("expiry"))
    expired = bool(expiry and expiry <= utc_now())
    valid = bool(token_doc.get("token")) and not expired
    scopes = token_doc.get("scopes") or SCOPES
    return TokenStatus(
        exists=True,
        valid=valid,
        expired=expired,
        has_refresh_token=bool(token_doc.get("refresh_token")),
        expiry=expiry.isoformat().replace("+00:00", "Z") if expiry else None,
        scopes=list(scopes),
        token_path=str(token_path),
    )


def authorize(credentials_path: Path, token_path: Path, force: bool) -> dict[str, Any]:
    """Run the installed-app OAuth2 flow and save a token."""
    Request, Credentials, InstalledAppFlow = require_google_auth()

    if not credentials_path.exists():
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    creds = None
    if token_path.exists() and not force:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.valid:
            save_token(token_path, creds)
            return {
                "action": "auth",
                "status": "already_valid",
                "tokenPath": str(token_path),
                "scopes": list(creds.scopes or SCOPES),
            }

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    save_token(token_path, creds)
    return {
        "action": "auth",
        "status": "authorized",
        "tokenPath": str(token_path),
        "scopes": list(creds.scopes or SCOPES),
        "expiry": creds.expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if creds.expiry
        else None,
    }


def refresh_token(token_path: Path) -> dict[str, Any]:
    """Refresh an existing token using its refresh token."""
    Request, Credentials, _ = require_google_auth()

    if not token_path.exists():
        raise FileNotFoundError(f"Token file not found: {token_path}")

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.refresh_token:
        raise ValueError("Token does not include a refresh token. Re-run the auth flow.")

    creds.refresh(Request())
    save_token(token_path, creds)
    return {
        "action": "refresh",
        "status": "refreshed",
        "tokenPath": str(token_path),
        "expiry": creds.expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if creds.expiry
        else None,
    }


def revoke_token(token_path: Path) -> dict[str, Any]:
    """Delete the local token file."""
    if not token_path.exists():
        return {"action": "revoke", "status": "not_found", "tokenPath": str(token_path)}
    token_path.unlink()
    return {"action": "revoke", "status": "deleted", "tokenPath": str(token_path)}


def parse_args() -> argparse.Namespace:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth", help="Run OAuth2 auth flow and save a token.")
    auth_parser.add_argument("--credentials", type=Path, required=True, help="OAuth client secret JSON.")
    auth_parser.add_argument("--token-path", type=Path, required=True, help="Where to save token JSON.")
    auth_parser.add_argument("--force", action="store_true", help="Ignore existing token and re-authorize.")

    status_parser = subparsers.add_parser("status", help="Inspect token status.")
    status_parser.add_argument("--token-path", type=Path, required=True, help="Existing token JSON.")

    refresh_parser = subparsers.add_parser("refresh", help="Refresh an existing token.")
    refresh_parser.add_argument("--token-path", type=Path, required=True, help="Existing token JSON.")

    revoke_parser = subparsers.add_parser("revoke", help="Delete the local token file.")
    revoke_parser.add_argument("--token-path", type=Path, required=True, help="Existing token JSON.")
    return parser.parse_args()


def main() -> int:
    """Entry point."""
    args = parse_args()

    try:
        if args.command == "auth":
            result = authorize(args.credentials, args.token_path, args.force)
        elif args.command == "status":
            result = {"action": "status", "status": "ok", **build_status(args.token_path).to_dict()}
        elif args.command == "refresh":
            result = refresh_token(args.token_path)
        elif args.command == "revoke":
            result = revoke_token(args.token_path)
        else:
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        LOG.error("calendar auth command failed", extra={"event": {"command": args.command, "error": str(exc)}})
        json.dump(
            {"ok": False, "error": str(exc), "command": args.command},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    json.dump({"ok": True, **result}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
