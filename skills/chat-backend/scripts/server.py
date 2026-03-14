#!/usr/bin/env python3
"""Stdlib-only REST + WebSocket chat backend for OpsClaw role agents."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import random
import socket
import struct
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from chat_backend_core import (
    CONFIG_DIR,
    DATA_DIR,
    ConfigManager,
    MessageStore,
    SessionManager,
    ensure_dirs,
    generate_ai_response,
    generate_agent_response,
    sanitize_config_for_client,
    utc_now_iso,
)


def json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class ChatHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "OpsClawChatHTTP/1.0"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Company-Id")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body) if body else {}

    def _resolve_company(self, query: Dict[str, Any]) -> Dict[str, Any]:
        company_id = query.get("company_id") or self.headers.get("X-Company-Id")
        return self.server.app["config_manager"].resolve_company(company_id)

    def _extract_token(self, query: Dict[str, Any]) -> Optional[str]:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return query.get("token")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Company-Id")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/api/config":
                config = self._resolve_company(query)
                payload = sanitize_config_for_client(config)
                payload["transport"] = {
                    "http_base_url": f"http://{self.server.bind_host}:{self.server.bind_port}",
                    "websocket_url": f"ws://{self.server.bind_host}:{self.server.app['ws_port']}/ws/<role>?token=<token>",
                }
                self._send_json(HTTPStatus.OK, payload)
                return
            if parsed.path == "/api/roles":
                config = self._resolve_company(query)
                payload = {"roles": sanitize_config_for_client(config)["role_list"]}
                self._send_json(HTTPStatus.OK, payload)
                return
            if parsed.path == "/api/history":
                role = query.get("role")
                limit = int(query.get("limit", "20"))
                token = self._extract_token(query)
                if not role:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing role query parameter."})
                    return
                if not token:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Missing session token."})
                    return
                session = self.server.app["session_manager"].validate(token)
                if not session:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid session token."})
                    return
                messages = self.server.app["message_store"].load_messages(
                    session["company_id"], role, session["user_id"], limit=limit
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "company_id": session["company_id"],
                        "role": role,
                        "user_id": session["user_id"],
                        "messages": messages,
                    },
                )
                return
        except FileNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/auth":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON request body."})
            return

        company_id = payload.get("company_id")
        employee_name = (payload.get("employee_name") or "").strip()
        employee_email = (payload.get("employee_email") or "").strip() or None

        if not company_id or not employee_name:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "company_id and employee_name are required."})
            return

        try:
            config = self.server.app["config_manager"].load(company_id)
        except FileNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return

        allowed_domains = config.get("auth", {}).get("allowed_domains", [])
        if employee_email and allowed_domains:
            email_domain = employee_email.split("@")[-1].lower() if "@" in employee_email else ""
            if email_domain not in {item.lower() for item in allowed_domains}:
                self._send_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": f"Email domain '{email_domain}' is not allowed for {company_id}."},
                )
                return

        session = self.server.app["session_manager"].create_session(company_id, employee_name, employee_email)
        self._send_json(
            HTTPStatus.OK,
            {
                "token": session["token"],
                "session": {
                    "company_id": session["company_id"],
                    "employee_name": session["employee_name"],
                    "employee_email": session["employee_email"],
                    "user_id": session["user_id"],
                    "issued_at": session["issued_at"],
                },
                "websocket_base_url": f"ws://{self.server.bind_host}:{self.server.app['ws_port']}/ws",
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.app["verbose"]:
            super().log_message(format, *args)


class ChatHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], app: Dict[str, Any]):
        super().__init__(server_address, handler_cls)
        self.app = app
        self.bind_host = server_address[0] or "127.0.0.1"
        self.bind_port = server_address[1]


async def read_http_headers(reader: asyncio.StreamReader) -> tuple[str, Dict[str, str]]:
    request_line = await reader.readline()
    if not request_line:
        raise ConnectionError("Client disconnected before sending a request line.")
    request_line_text = request_line.decode("utf-8").strip()
    headers: Dict[str, str] = {}
    while True:
        line = await reader.readline()
        if not line:
            break
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return request_line_text, headers


async def websocket_send_json(writer: asyncio.StreamWriter, payload: Dict[str, Any]) -> None:
    data = json_bytes(payload)
    header = bytearray()
    header.append(0x81)
    length = len(data)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))
    writer.write(bytes(header) + data)
    await writer.drain()


async def websocket_read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    first_two = await reader.readexactly(2)
    first_byte, second_byte = first_two[0], first_two[1]
    opcode = first_byte & 0x0F
    masked = bool(second_byte & 0x80)
    payload_length = second_byte & 0x7F
    if payload_length == 126:
        payload_length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif payload_length == 127:
        payload_length = struct.unpack("!Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(payload_length)
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


async def websocket_close(writer: asyncio.StreamWriter, code: int = 1000, reason: str = "") -> None:
    payload = struct.pack("!H", code) + reason.encode("utf-8")
    header = bytearray([0x88])
    length = len(payload)
    if length < 126:
        header.append(length)
    else:
        header.append(126)
        header.extend(struct.pack("!H", length))
    writer.write(bytes(header) + payload)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def handle_websocket_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    app: Dict[str, Any],
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        request_line, headers = await read_http_headers(reader)
        method, raw_target, _http_version = request_line.split(" ", 2)
        parsed = urlparse(raw_target)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        if method.upper() != "GET" or not parsed.path.startswith("/ws/"):
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        token = query.get("token")
        if not token:
            writer.write(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        session = app["session_manager"].validate(token)
        if not session:
            writer.write(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        config = app["config_manager"].load(session["company_id"])
        role = parsed.path.rsplit("/", 1)[-1]
        role_data = config.get("roles", {}).get(role)
        if not role_data:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            return

        websocket_key = headers.get("sec-websocket-key", "")
        accept_key = base64.b64encode(
            hashlib.sha1((websocket_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")).digest()
        ).decode("ascii")
        response_headers = [
            "HTTP/1.1 101 Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {accept_key}",
            "",
            "",
        ]
        writer.write("\r\n".join(response_headers).encode("utf-8"))
        await writer.drain()

        await websocket_send_json(
            writer,
            {
                "type": "connected",
                "role": role,
                "agent_name": role_data.get("display_name", role.title()),
                "timestamp": utc_now_iso(),
                "greeting": role_data.get("greeting", ""),
            },
        )

        while True:
            opcode, payload = await websocket_read_frame(reader)
            if opcode == 0x8:
                break
            if opcode == 0x9:
                writer.write(b"\x8A\x00")
                await writer.drain()
                continue
            if opcode != 0x1:
                continue
            try:
                message = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                await websocket_send_json(writer, {"type": "error", "error": "Invalid JSON payload."})
                continue
            if message.get("type") != "message":
                await websocket_send_json(writer, {"type": "error", "error": "Unsupported message type."})
                continue
            if message.get("role") and message.get("role") != role:
                await websocket_send_json(writer, {"type": "error", "error": "Message role does not match socket role."})
                continue

            text = (message.get("text") or "").strip()
            if not text:
                await websocket_send_json(writer, {"type": "error", "error": "Message text is required."})
                continue

            app["message_store"].append_message(
                session["company_id"],
                role,
                session["user_id"],
                sender="user",
                text=text,
            )
            history = app["message_store"].load_messages_for_ai(
                session["company_id"],
                role,
                session["user_id"],
                limit=10,
            )
            await websocket_send_json(
                writer,
                {
                    "type": "typing",
                    "agent_name": role_data.get("display_name", role.title()),
                    "timestamp": utc_now_iso(),
                },
            )
            typing_started_at = asyncio.get_running_loop().time()
            ai_text = await asyncio.to_thread(
                generate_ai_response,
                config,
                role,
                text,
                session["employee_name"],
                history,
            )
            if ai_text:
                response = {
                    "type": "response",
                    "text": ai_text,
                    "agent_name": role_data.get("display_name", role.title()),
                    "timestamp": utc_now_iso(),
                }
                target_delay = random.uniform(0.5, 1.5)
                elapsed = asyncio.get_running_loop().time() - typing_started_at
                remaining = target_delay - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            else:
                await asyncio.sleep(0.35)
                response = generate_agent_response(config, role, text, session["employee_name"])
            app["message_store"].append_message(
                session["company_id"],
                role,
                session["user_id"],
                sender="agent",
                text=response["text"],
                agent_name=response["agent_name"],
                timestamp=response["timestamp"],
            )
            await websocket_send_json(writer, response)
    except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
        pass
    except Exception as exc:
        if app["verbose"]:
            print(f"websocket error from {peer}: {exc}", flush=True)
    finally:
        if not writer.is_closing():
            try:
                await websocket_close(writer)
            except Exception:
                writer.close()
                await writer.wait_closed()


async def run_websocket_server(host: str, port: int, app: Dict[str, Any]) -> None:
    server = await asyncio.start_server(lambda r, w: handle_websocket_client(r, w, app), host=host, port=port)
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    print(f"OpsClaw chat WebSocket server listening on {sockets}", flush=True)
    async with server:
        await server.serve_forever()


def run_http_server(host: str, port: int, app: Dict[str, Any]) -> None:
    httpd = ChatHTTPServer((host, port), ChatHTTPRequestHandler, app)
    print(f"OpsClaw chat HTTP server listening on http://{host}:{port}", flush=True)
    httpd.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OpsClaw chat backend.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for both HTTP and WebSocket servers.")
    parser.add_argument("--http-port", type=int, default=8000, help="Port for REST endpoints.")
    parser.add_argument("--ws-port", type=int, default=8765, help="Port for WebSocket connections.")
    parser.add_argument("--config-dir", type=Path, default=CONFIG_DIR, help="Directory containing company config JSON files.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Directory used for sessions and message history.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose request logging.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dirs()
    config_manager = ConfigManager(args.config_dir)
    message_store = MessageStore(args.data_dir)
    session_manager = SessionManager(args.data_dir / "sessions.json")
    app = {
        "config_manager": config_manager,
        "message_store": message_store,
        "session_manager": session_manager,
        "ws_port": args.ws_port,
        "verbose": args.verbose,
    }

    http_thread = threading.Thread(target=run_http_server, args=(args.host, args.http_port, app), daemon=True)
    http_thread.start()
    try:
        asyncio.run(run_websocket_server(args.host, args.ws_port, app))
    except KeyboardInterrupt:
        print("Shutting down chat backend.", flush=True)


if __name__ == "__main__":
    main()
