"""Dashboard HTTP server: stdlib only, a thin shell over autopsy and revive.

Hosted mode accepts bundled sample ids only. Local mode also accepts a directory path or an
uploaded zip, and binds to loopback only. Runs execute in background threads and report real
stage events and real proof output lines over Server-Sent Events.

Caveat: ``prove`` runs the repaired project in a temp venv with a minimal environment, but the
process is not sandboxed. That is why hosted mode never accepts user code.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import stat
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .. import __version__, scan, verify
from .. import autopsy as autopsy_mod
from .. import revive as revive_mod
from . import results

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "lib.js": "text/javascript; charset=utf-8",
}
REPO_ROOT = Path(__file__).resolve().parents[3]

JSON_BODY_CAP = 64 * 1024
UPLOAD_CAP = 50 * 1024 * 1024
UPLOAD_MAX_FILES = 5000
MAX_CONCURRENT_RUNS = 4
KEEP_RUNS = 50
KEEP_UPLOADS = 50
LOG_EVENT_CAP = 2000
SSE_KEEPALIVE = 15.0
STAGES = ("autopsy", "copy", "repair", "reanalyze", "validate", "dockerfile", "prove")
_ID = re.compile(r"^[0-9a-f]{32}$")


class ConfigError(ValueError):
    """Invalid server configuration."""


class ApiError(Exception):
    def __init__(self, status: int, error: str, detail: str = "") -> None:
        super().__init__(detail or error)
        self.status, self.error, self.detail = status, error, detail


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


# ------------------------------------------------------------------------------ samples


def list_samples(samples_dir: Path | None) -> list[dict[str, Any]]:
    """Describe every directory under samples_dir. Data driven: nothing is hardcoded."""
    if samples_dir is None or not samples_dir.is_dir():
        return []
    out = []
    for d in sorted(p for p in samples_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        files = []
        for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
            dirnames[:] = sorted(x for x in dirnames if x not in scan.IGNORED_DIRS)
            for name in sorted(filenames):
                full = Path(dirpath) / name
                if full.is_symlink():
                    continue
                files.append({"path": full.relative_to(d).as_posix(), "size": full.stat().st_size})
        files.sort(key=lambda f: f["path"])
        title = d.name
        readme = d / "README.md"
        if readme.is_file():
            first = readme.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
            if first and first[0].startswith("#"):
                heading = first[0].lstrip("# ").strip()
                title = heading.split(": ", 1)[1] if ": " in heading else heading or d.name
        out.append(
            {
                "id": d.name,
                "title": title,
                "files": files,
                "python_files": sum(1 for f in files if f["path"].endswith(".py")),
            }
        )
    return out


# ------------------------------------------------------------------------------ uploads


def safe_extract(data: bytes, dest: Path) -> int:
    """Extract a zip into dest, refusing anything unsafe. Returns the file count."""
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise ApiError(400, "bad_zip", "the upload is not a valid zip archive") from None
    infos = zf.infolist()
    if len(infos) > UPLOAD_MAX_FILES:
        raise ApiError(413, "too_many_files", f"more than {UPLOAD_MAX_FILES} entries")
    if sum(i.file_size for i in infos) > UPLOAD_CAP:
        raise ApiError(413, "too_large", "uncompressed size exceeds 50 MB")
    root = dest.resolve()
    targets: list[tuple[zipfile.ZipInfo, Path]] = []
    for info in infos:
        name = info.filename
        parts = name.replace("\\", "/").split("/")
        if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or ".." in parts or "\x00" in name:
            raise ApiError(400, "unsafe_path", "the archive contains an unsafe path")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ApiError(400, "symlink", "the archive contains a symlink")
        target = (root / name).resolve()
        if target != root and root not in target.parents:
            raise ApiError(400, "unsafe_path", "the archive contains an unsafe path")
        targets.append((info, target))
    count = 0
    try:
        for info, target in targets:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read(UPLOAD_CAP + 1))
            count += 1
    except OSError:  # e.g. a path used as both a file and a directory
        raise ApiError(400, "bad_zip", "the archive has conflicting file and directory paths") from None
    return count


# ------------------------------------------------------------------------------ runs


class Run:
    def __init__(self, run_id: str, source: dict[str, str], prove: bool, node: bool = False) -> None:
        self.id = run_id
        self.source = source
        self.prove = prove
        self.node = node
        self.state = "queued"
        self.events: list[dict[str, Any]] = []
        self.stages = {s: {"name": s, "status": "pending", "message": "", "duration_s": None} for s in STAGES if prove or s != "prove"}
        self.result: dict[str, Any] | None = None
        self.cond = threading.Condition()
        self._started = time.monotonic()
        self._stage_t: dict[str, float] = {}
        self._log_count = 0
        self.finished = False

    # callers hold no lock; every mutation goes through emit()
    def emit(self, etype: str, **data: Any) -> None:
        with self.cond:
            event = {"id": len(self.events) + 1, "type": etype, "t": round(time.monotonic() - self._started, 3), **data}
            self.events.append(event)
            self.cond.notify_all()

    def on_event(self, stage: str, status: str, message: str) -> None:
        now = time.monotonic()
        with self.cond:
            st = self.stages.get(stage)
            if st is not None:
                if status == "start":
                    st["status"] = "running"
                    self._stage_t[stage] = now
                else:
                    st["status"] = "done"
                    st["duration_s"] = round(now - self._stage_t.get(stage, now), 3)
                st["message"] = message
        self.emit("stage", stage=stage, status=status, message=message)

    def on_line(self, line: str) -> None:
        with self.cond:
            self._log_count += 1
            n = self._log_count
        if n <= LOG_EVENT_CAP:
            self.emit("log", stage="prove", message=line)
        elif n == LOG_EVENT_CAP + 1:
            self.emit("log", stage="prove", message="[further output omitted from the live stream; see the final result]")

    def finish(self, state: str, result: dict[str, Any]) -> None:
        with self.cond:
            for st in self.stages.values():
                if st["status"] == "running":
                    st["status"] = "error" if state == "error" else "done"
                elif st["status"] == "pending":
                    st["status"] = "skipped"
            self.state = state
            self.result = result
            self.finished = True
        self.emit("end", state=state, outcome=result.get("outcome"), reason=result.get("reason"))

    def snapshot(self) -> dict[str, Any]:
        with self.cond:
            return {
                "run_id": self.id,
                "state": self.state,
                "source": self.source,
                "prove": self.prove,
                "node": self.node,
                "stages": list(self.stages.values()),
                "events": list(self.events),
                "result": self.result,
            }


@dataclass
class Config:
    mode: str = "hosted"
    host: str = "127.0.0.1"
    port: int = 8765
    wheelhouse: Path | None = None
    samples_dir: Path | None = None


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: Config) -> None:
        if config.mode not in ("hosted", "local"):
            raise ConfigError("mode must be 'hosted' or 'local'")
        if config.mode == "local" and not is_loopback(config.host):
            raise ConfigError("local mode binds to a loopback host only (127.0.0.1, ::1 or localhost)")
        if config.wheelhouse is None and (REPO_ROOT / "wheelhouse").is_dir():
            config.wheelhouse = REPO_ROOT / "wheelhouse"
        if config.samples_dir is None and (REPO_ROOT / "samples").is_dir():
            config.samples_dir = REPO_ROOT / "samples"
        if config.wheelhouse is not None and not config.wheelhouse.is_dir():
            raise ConfigError(f"wheelhouse is not a directory: {config.wheelhouse}")
        self.config = config
        self.workspace = Path(tempfile.mkdtemp(prefix="grimoire-dashboard-"))
        (self.workspace / "uploads").mkdir()
        self.runs: dict[str, Run] = {}
        self.uploads: list[str] = []
        self.lock = threading.Lock()
        self._closed = False
        if ":" in config.host:
            self.address_family = socket.AF_INET6
        try:
            super().__init__((config.host, config.port), Handler)
        except BaseException:
            shutil.rmtree(self.workspace, ignore_errors=True)
            raise

    def allowed_hosts(self) -> set[str] | None:
        """Accepted Host header values, or None to accept any (hosted on a public interface)."""
        port = self.server_address[1]
        bound = self.config.host
        if self.config.mode == "hosted" and not is_loopback(bound):
            return None
        return {f"{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")} | {f"{bound}:{port}"}

    def server_close(self) -> None:
        super().server_close()
        if not self._closed:
            self._closed = True
            shutil.rmtree(self.workspace, ignore_errors=True)

    # -- sources
    def resolve_source(self, body: dict[str, Any]) -> tuple[str, dict[str, str]]:
        keys = [k for k in ("sample", "path", "upload") if k in body]
        if len(keys) != 1:
            raise ApiError(400, "bad_request", "provide exactly one of sample, path or upload")
        key = keys[0]
        value = body[key]
        if not isinstance(value, str) or not value:
            raise ApiError(400, "bad_request", f"{key} must be a non-empty string")
        if key == "sample":
            samples = {s["id"] for s in list_samples(self.config.samples_dir)}
            if value not in samples:
                raise ApiError(404, "unknown_sample", "no such sample")
            assert self.config.samples_dir is not None
            return str(self.config.samples_dir / value), {"kind": "sample", "id": value}
        if self.config.mode != "local":
            raise ApiError(403, "forbidden", f"{key} sources are only available in local mode")
        if key == "path":
            if "\x00" in value:
                raise ApiError(400, "invalid_path", "the path is not valid")
            path = Path(value).expanduser()
            if not path.is_dir():
                raise ApiError(400, "invalid_path", "the path is not a readable directory")
            return str(path.resolve()), {"kind": "path", "id": path.resolve().name}
        if not _ID.match(value) or value not in self.uploads:
            raise ApiError(404, "unknown_upload", "no such upload")
        return str(self.workspace / "uploads" / value), {"kind": "upload", "id": value}

    # -- runs
    def start_run(self, source_path: str, source: dict[str, str], prove: bool, node: bool = False) -> Run:
        with self.lock:
            active = sum(1 for r in self.runs.values() if not r.finished)
            if active >= MAX_CONCURRENT_RUNS:
                raise ApiError(429, "too_many_runs", f"at most {MAX_CONCURRENT_RUNS} runs may be active")
            run = Run(uuid.uuid4().hex, source, prove, node)
            self.runs[run.id] = run
            while len(self.runs) > KEEP_RUNS:
                oldest = next((rid for rid, r in self.runs.items() if r.finished), None)
                if oldest is None:
                    break
                del self.runs[oldest]
        threading.Thread(target=self._execute, args=(run, source_path), daemon=True).start()
        return run

    def _execute(self, run: Run, source_path: str) -> None:
        with run.cond:
            run.state = "running"
        run.emit("state", state="running")
        try:
            report = revive_mod.revive(
                source_path,
                prove=run.prove,
                node=run.node,
                wheelhouse=self.config.wheelhouse,
                on_event=run.on_event,
                on_line=run.on_line,
            )
            run.finish("done", results.result_payload(report))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            run.emit("error", message="internal error; see the server log")
            run.finish("error", results.failure_payload("internal error while running the pipeline"))

    def store_upload(self, data: bytes) -> str:
        upload_id = uuid.uuid4().hex
        dest = self.workspace / "uploads" / upload_id
        dest.mkdir()
        try:
            safe_extract(data, dest)
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        with self.lock:
            self.uploads.append(upload_id)
            while len(self.uploads) > KEEP_UPLOADS:
                shutil.rmtree(self.workspace / "uploads" / self.uploads.pop(0), ignore_errors=True)
        return upload_id


class Handler(BaseHTTPRequestHandler):
    server: DashboardServer
    protocol_version = "HTTP/1.1"
    server_version = "Grimoire"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write("grimoire dashboard: " + format % args + "\n")

    # -- plumbing
    def _security_headers(self) -> None:
        self.send_header("Content-Security-Policy", "default-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self.close_connection = True
        try:
            body = json.dumps({"error": "http_error", "detail": message or self.responses.get(code, ("", ""))[0]}).encode()
            self.send_response(code)
            self._security_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except OSError:
            pass

    def _check_host(self) -> None:
        allowed = self.server.allowed_hosts()
        host = self.headers.get("Host", "")
        if allowed is not None and host.lower() not in allowed:
            raise ApiError(403, "bad_host", "unrecognized Host header")

    def _check_origin(self) -> None:
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{self.headers.get('Host', '')}":
            raise ApiError(403, "bad_origin", "cross-origin requests are not allowed")

    def _read_body(self, cap: int, ctype: str) -> bytes:
        got = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if got != ctype:
            raise ApiError(415, "unsupported_media_type", f"Content-Type must be {ctype}")
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            raise ApiError(411, "length_required", "a Content-Length header is required")
        if int(length) > cap:
            self.close_connection = True
            raise ApiError(413, "too_large", f"body exceeds {cap} bytes")
        return self.rfile.read(int(length))

    def _json_body(self) -> dict[str, Any]:
        raw = self._read_body(JSON_BODY_CAP, "application/json")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "bad_json", "the request body is not valid JSON") from None
        if not isinstance(body, dict):
            raise ApiError(400, "bad_json", "the request body must be a JSON object")
        return body

    def _dispatch(self, fn: Any) -> None:
        try:
            self._check_host()
            fn()
        except ApiError as exc:
            if self.command == "POST":  # the body may be unread
                self.close_connection = True
            self._json(exc.status, {"error": exc.error, "detail": exc.detail})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self.close_connection = True
            try:
                self._json(500, {"error": "internal_error", "detail": "internal error; see the server log"})
            except OSError:
                pass

    # -- GET
    def do_GET(self) -> None:
        self._dispatch(self._get)

    def do_HEAD(self) -> None:
        self._dispatch(self._get)

    def _get(self) -> None:
        path = unquote(urlsplit(self.path).path)
        srv = self.server
        if path == "/api/health":
            wh = srv.config.wheelhouse
            wheels = sorted(p.name for p in wh.glob("*.whl")) if wh else []
            return self._json(
                200,
                {
                    "status": "ok",
                    "mode": srv.config.mode,
                    "version": __version__,
                    "wheelhouse": {"in_use": wh is not None, "wheels": len(wheels)},
                },
            )
        if path == "/api/samples":
            return self._json(200, {"samples": list_samples(srv.config.samples_dir)})
        m = re.fullmatch(r"/api/runs/([0-9a-f]{32})(/events)?", path)
        if m:
            run = srv.runs.get(m.group(1))
            if run is None:
                raise ApiError(404, "unknown_run", "no such run")
            return self._stream(run) if m.group(2) else self._json(200, run.snapshot())
        if path.startswith("/api/"):
            raise ApiError(404, "not_found", "no such endpoint")
        if path == "/favicon.ico":  # no icon is shipped; answer 204 so browsers log no error
            self.send_response(204)
            self._security_headers()
            self.end_headers()
            return
        name = "index.html" if path == "/" else path.lstrip("/")
        if name in STATIC_FILES and (STATIC_DIR / name).is_file():
            return self._send(200, (STATIC_DIR / name).read_bytes(), STATIC_FILES[name])
        raise ApiError(404, "not_found", "not found")

    def _stream(self, run: Run) -> None:
        last = self.headers.get("Last-Event-ID", "")
        index = int(last) if last.isdigit() else 0
        self.send_response(200)
        self._security_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command == "HEAD":
            return
        try:
            while True:
                with run.cond:
                    if index >= len(run.events) and not run.finished:
                        run.cond.wait(timeout=SSE_KEEPALIVE)
                    batch = run.events[index:]
                    done = run.finished
                if batch:
                    for ev in batch:
                        data = json.dumps(ev)
                        self.wfile.write(f"id: {ev['id']}\nevent: {ev['type']}\ndata: {data}\n\n".encode())
                    index += len(batch)
                    self.wfile.flush()
                    if batch[-1]["type"] == "end":
                        return
                elif done:
                    return
                else:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    # -- POST
    @staticmethod
    def _node_flag(body: dict[str, Any]) -> bool:
        node = body.get("node", False)
        if not isinstance(node, bool):
            raise ApiError(400, "bad_request", "node must be true or false")
        return node

    def do_POST(self) -> None:
        self._dispatch(self._post)

    def _post(self) -> None:
        self._check_origin()
        path = urlsplit(self.path).path
        srv = self.server
        if path == "/api/upload":
            if srv.config.mode != "local":
                raise ApiError(403, "forbidden", "uploads are only available in local mode")
            data = self._read_body(UPLOAD_CAP, "application/zip")
            return self._json(201, {"upload_id": srv.store_upload(data)})
        if path == "/api/autopsy":
            body = self._json_body()
            node = self._node_flag(body)
            source_path, source = srv.resolve_source({k: v for k, v in body.items() if k != "node"})
            report = autopsy_mod.autopsy(source_path, node=node)
            return self._json(200, {"source": source, **results.autopsy_payload(report)})
        if path == "/api/runs":
            body = self._json_body()
            prove = body.get("prove", True)
            if not isinstance(prove, bool):
                raise ApiError(400, "bad_request", "prove must be true or false")
            node = self._node_flag(body)
            source_path, source = srv.resolve_source({k: v for k, v in body.items() if k not in ("prove", "node")})
            run = srv.start_run(source_path, source, prove, node)
            return self._json(202, {"run_id": run.id})
        raise ApiError(404, "not_found", "no such endpoint")


def serve(config: Config) -> int:
    """Run the dashboard until interrupted. Returns a process exit code."""
    try:
        server = DashboardServer(config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"error: cannot bind {config.host}:{config.port}: {exc.strerror or exc}", file=sys.stderr)
        return 3
    host, port = server.server_address[:2]
    shown = f"[{host}]" if ":" in str(host) else host
    print(f"Grimoire dashboard ({config.mode} mode): http://{shown}:{port}/", flush=True)
    if config.mode == "local":
        print("local mode: prove runs repository code outside a sandbox. Use it on your own code only.", file=sys.stderr)
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, signal.default_int_handler)  # SIGTERM shuts down as cleanly as Ctrl-C
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down", file=sys.stderr)
    finally:
        server.server_close()
    return 0
