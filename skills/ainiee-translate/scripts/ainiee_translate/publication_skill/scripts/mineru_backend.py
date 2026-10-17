"""Durable acquisition of real MinerU cloud result archives.

This module deliberately does not import extraction records or split PDFs. A caller
supplies a prepared derivative of at most 100 pages and 190 MB. New uploads require
``allow_upload=True``; an existing batch can be polled without that permission.
Credentials are read in memory and never written to the checkpoint or returned.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

API_BASE = "https://mineru.net"
MAX_PAGES = 100
MAX_PDF_BYTES = 190_000_000
MAX_BUNDLE_BYTES = 1_073_741_824
MAX_UNPACKED_BYTES = 4_294_967_296
CHECKPOINT_SCHEMA = "mineru-acquisition/1"
_BATCH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)


class MinerUError(ValueError):
    """A local validation or safely reported MinerU API error."""


class _Busy(Exception):
    pass


class _APIError(MinerUError):
    pass


def _safe(message, token=None):
    """Remove credentials and signed query strings from diagnostic text."""
    value = str(message)
    if token:
        value = value.replace(token, "[redacted]")
    value = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", value)

    def clean_url(match):
        try:
            parsed = urllib.parse.urlsplit(match.group(0))
            host = parsed.hostname or "[host]"
            if parsed.port:
                host += ":" + str(parsed.port)
            return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except ValueError:
            return "[URL]"

    value = _URL.sub(clean_url, value)
    value = re.sub(r"(?i)(token|authorization|api[_-]?key)\s*[:=]\s*\S+", r"\1=[redacted]", value)
    return " ".join(value.split())[:500]


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _save(path, state):
    path = Path(path)
    state["updated_at"] = _now()
    temporary = path.with_name(path.name + ".tmp." + str(os.getpid()))
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


@contextmanager
def _lock(path):
    """An OS-held lock is released even if the acquiring process exits."""
    with Path(path).open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise _Busy from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _credential(config_path=None):
    value = os.environ.get("MINERU_TOKEN", "").strip()
    source = "MINERU_TOKEN" if value else None
    if not value:
        path = Path(config_path) if config_path else Path.home() / ".mineru" / "config.yaml"
        if path.is_file():
            if path.stat().st_size > 65_536:
                raise MinerUError("MinerU config is too large; expected a scalar token setting.")
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            matches = [re.fullmatch(r"token\s*:\s*(.*?)\s*", line) for line in lines]
            scalars = [match.group(1) for match in matches if match]
            if len(scalars) > 1:
                raise MinerUError("MinerU config contains duplicate token settings.")
            if scalars:
                scalar = scalars[0]
                if scalar.startswith('"'):
                    # JSON double-quoted strings form a safe subset of YAML scalars.
                    try:
                        value, end = json.JSONDecoder().raw_decode(scalar)
                        tail = scalar[end:].strip()
                        if tail and not tail.startswith("#"):
                            raise ValueError
                    except (ValueError, TypeError):
                        raise MinerUError("MinerU token must be a simple YAML scalar.") from None
                elif scalar.startswith("'"):
                    match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", scalar)
                    if not match:
                        raise MinerUError("MinerU token must be a simple YAML scalar.")
                    value = match.group(1).replace("''", "'")
                else:
                    value = re.sub(r"\s+#.*$", "", scalar).strip()
                    if value[:1] in "{}[]&*!|>@" or value.lower() in {"null", "~"}:
                        value = ""
                source = "~/.mineru/config.yaml" if value else None
    if value and (not isinstance(value, str) or re.search(r"\s", value)):
        raise MinerUError("MinerU token must be a nonempty scalar without whitespace.")
    return value or None, source


def find_cli(explicit=None):
    """Return a real CLI path, or None; an invalid explicit setting never falls back."""
    setting = explicit if explicit is not None else os.environ.get("MINERU_CLI")
    if setting is not None:
        setting = os.fspath(setting)
        path = Path(setting).expanduser()
        return str(path.resolve()) if path.is_file() else shutil.which(setting)
    found = shutil.which("mineru-open-api")
    if found:
        return found
    directory = Path.home() / ".mineru" / "bin"
    for name in ("mineru-open-api.exe", "mineru-open-api"):
        path = directory / name
        if path.is_file():
            return str(path)
    return None


def probe(explicit=None):
    """Report credential presence and a CLI version without exposing credentials."""
    token = None
    try:
        token, source = _credential()
        credential = {"present": bool(token), "source": source,
                      "status": "available" if token else "missing"}
    except (OSError, UnicodeError, MinerUError) as exc:
        credential = {"present": False, "source": None, "status": "invalid",
                      "error": _safe(exc)}
    binary = find_cli(explicit)
    cli = {"path": binary, "status": "missing", "version": None}
    if binary:
        try:
            result = subprocess.run([binary, "--version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=10)
            text = result.stdout.strip() or result.stderr.strip()
            cli.update(status="available" if result.returncode == 0 else "error",
                       version=_safe(text.splitlines()[0] if text else "", token),
                       returncode=result.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            cli.update(status="error", error=_safe(exc, token))
    return {"credential": credential, "cli": cli, "api_base": API_BASE,
            "transport": "MinerU v4 batch API", "chunk_limits":
            {"pages": MAX_PAGES, "bytes": MAX_PDF_BYTES}}


def _options(options):
    supplied = dict(options) if isinstance(options, Mapping) else vars(options)
    normalized = {"model": supplied.get("model", "vlm"),
                  "language": supplied.get("language", "ch"),
                  "ocr": supplied.get("ocr", True),
                  "api_base": supplied.get("api_base", API_BASE)}
    for key in ("model", "language"):
        if not isinstance(normalized[key], str) or not re.fullmatch(r"[A-Za-z0-9_+-]{1,32}", normalized[key]):
            raise MinerUError("MinerU " + key + " must be a short identifier.")
    if not isinstance(normalized["ocr"], bool):
        raise MinerUError("MinerU ocr option must be a Boolean.")
    base = normalized["api_base"]
    if not isinstance(base, str):
        raise MinerUError("MinerU api_base must be an HTTPS URL.")
    parsed = urllib.parse.urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        raise MinerUError("MinerU api_base must be an HTTPS URL without credentials or query parameters.")
    normalized["api_base"] = base.rstrip("/")
    return normalized


def _source(pdf_path):
    path = Path(pdf_path).resolve()
    if not path.is_file():
        raise MinerUError("MinerU input PDF does not exist.")
    size = path.stat().st_size
    if size <= 0 or size > MAX_PDF_BYTES:
        raise MinerUError("MinerU input must be nonempty and no larger than 190 MB; split a derivative first.")
    try:
        import pymupdf
    except ImportError:
        raise MinerUError("PyMuPDF is required to validate MinerU derivative PDFs.") from None
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.needs_pass:
                raise MinerUError("MinerU input must be an accessible, unencrypted PDF derivative.")
            count = len(document)
    except MinerUError:
        raise
    except Exception:
        raise MinerUError("MinerU input is not a readable PDF.") from None
    if count <= 0 or count > MAX_PAGES:
        raise MinerUError("MinerU derivative must contain 1 to 100 pages; split it first.")
    return path, {"sha256": _sha(path), "bytes": size, "pages": count}


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.has_header("Authorization"):
            raise urllib.error.URLError("Authenticated API redirect refused.")
        _url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _SignedUploadHeaders(urllib.request.BaseHandler):
    # AbstractHTTPHandler automatically adds application/x-www-form-urlencoded
    # to a body without Content-Type. Run after its request preparation: MinerU's
    # official SDK sends a raw PUT with no Content-Type, as required by the signed
    # storage URL. API JSON requests keep their own Content-Type and authorization.
    handler_order = 900

    def http_request(self, request):
        if getattr(request, "_mineru_signed_upload", False):
            request.remove_header("Content-type")
            request.remove_header("Authorization")
        return request

    https_request = http_request


def _open(request, timeout=30):
    return urllib.request.build_opener(_SafeRedirect(), _SignedUploadHeaders()).open(request, timeout=timeout)


def _url(value):
    if not isinstance(value, str):
        raise MinerUError("MinerU returned an invalid artifact URL.")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise MinerUError("MinerU artifact URL must use HTTPS without embedded credentials.")
    return value


def _api(method, url, token, payload=None):
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method,
                                     headers={"Authorization": "Bearer " + token,
                                              "Content-Type": "application/json",
                                              "User-Agent": "pdf-to-epub/mineru-v4"})
    with _open(request, timeout=30) as response:
        raw = response.read(8_388_609)
    if len(raw) > 8_388_608:
        raise MinerUError("MinerU API response exceeds the safety limit.")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise MinerUError("MinerU API returned invalid JSON.") from None
    if not isinstance(result, dict):
        raise MinerUError("MinerU API returned an invalid response shape.")
    if result.get("code") not in (0, "0"):
        raise _APIError(_safe(result.get("msg") or result.get("message") or "MinerU API rejected the request.", token))
    data = result.get("data")
    if not isinstance(data, dict):
        raise MinerUError("MinerU API response has no data object.")
    return data


def _storage_error(error, url):
    """Retain a bounded storage error code/reason, never its raw signed body."""
    code, message = None, None
    try:
        raw = error.read(65_537)
        if len(raw) <= 65_536:
            try:
                root = ET.fromstring(raw)
                fields = {node.tag.rsplit("}", 1)[-1]: node.text for node in root.iter()}
                code, message = fields.get("Code"), fields.get("Message")
            except (ET.ParseError, ValueError):
                try:
                    fields = json.loads(raw)
                    if isinstance(fields, dict):
                        code = fields.get("Code") or fields.get("code")
                        message = fields.get("Message") or fields.get("message")
                except (ValueError, UnicodeError):
                    pass
    except Exception:
        pass
    finally:
        error.close()
    diagnostic = "MinerU signed upload failed (HTTP " + str(error.code)
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", code):
        diagnostic += ", code " + code
    diagnostic += ")."
    if isinstance(message, str) and message.strip():
        # Storage can echo signing material in an error message. Remove every
        # nontrivial value from this signed URL before sanitizing any explanation.
        for _, value in urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query):
            if len(value) >= 6:
                message = message.replace(value, "[redacted]")
        diagnostic += " " + _safe(message)
    return MinerUError(diagnostic)


def _upload(path, url, expected_sha=None):
    # Signed storage endpoints must never receive the MinerU Bearer token.
    with Path(path).open("rb") as stream:
        if expected_sha:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            if digest.hexdigest() != expected_sha:
                raise MinerUError("Derivative PDF changed after fingerprinting; the preserved batch was not uploaded.")
            stream.seek(0)
        request = urllib.request.Request(_url(url), data=stream, method="PUT",
                                         headers={"Content-Length": str(os.fstat(stream.fileno()).st_size)})
        request._mineru_signed_upload = True
        try:
            with _open(request, timeout=60) as response:
                response.read(1024)
        except urllib.error.HTTPError as exc:
            raise _storage_error(exc, url) from None


def _validate_bundle(path):
    if not zipfile.is_zipfile(path):
        raise MinerUError("MinerU result is not a valid ZIP archive.")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > 100_000 or sum(item.file_size for item in entries) > MAX_UNPACKED_BYTES:
                raise MinerUError("MinerU result archive exceeds the validation limits.")
            if archive.testzip() is not None:
                raise MinerUError("MinerU result archive failed its CRC check.")
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise MinerUError("MinerU result archive cannot be read safely.") from None


def _download(url, bundle):
    partial = bundle.with_suffix(".zip.part")
    request = urllib.request.Request(_url(url), method="GET")
    with _open(request, timeout=60) as response, partial.open("wb") as stream:
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BUNDLE_BYTES:
                raise MinerUError("MinerU result download exceeds 1 GiB.")
            stream.write(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    _validate_bundle(partial)
    partial.replace(bundle)


def _progress(record, token):
    progress = {"state": str(record.get("state", "pending"))}
    incoming = record.get("extract_progress")
    if isinstance(incoming, dict):
        for key in ("extracted_pages", "total_pages"):
            if isinstance(incoming.get(key), (int, float)) and not isinstance(incoming.get(key), bool):
                progress[key] = incoming[key]
    if record.get("err_msg"):
        progress["message"] = _safe(record["err_msg"], token)
    return progress


def _result(state, checkpoint, status=None, message=None, cached=False):
    progress = dict(state.get("progress") or {"state": state.get("status", "pending")})
    if message:
        progress["message"] = _safe(message)
    final_status = status or state.get("status", "pending")
    return {"status": final_status, "bundle": checkpoint.parent / "bundle.zip" if final_status == "done" else None,
            "batch_id": state.get("batch_id"), "request_fingerprint": state["request_fingerprint"],
            "progress": progress, "checkpoint": checkpoint, "cached": cached}


def ensure_bundle(pdf_path, job_dir, options, allow_upload=False, wait_seconds=30, batch_id=None):
    """Acquire/cache a MinerU ZIP and return safe, resumable acquisition metadata.

    ``options`` accepts a mapping or argparse namespace with model='vlm',
    language='ch', ocr=True, api_base='https://mineru.net'. ``wait_seconds`` bounds
    repeated polling, not transfer time; zero performs one status request. Request
    data lives in job_dir/<fingerprint>/checkpoint.json and bundle.zip. An optional
    existing ``batch_id`` is adopted without submitting or uploading a PDF.

    Status is done, upload_required, credential_required, submission_unknown,
    pending, running, waiting-file, failed, error, or busy. Network failure leaves
    the batch checkpoint in place. The returned bundle is a Path only when done.
    """
    if not isinstance(allow_upload, bool):
        raise MinerUError("allow_upload must be explicitly Boolean.")
    if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float)) or not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise MinerUError("wait_seconds must be a finite nonnegative number.")
    if batch_id is not None and (not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id)):
        raise MinerUError("MinerU batch_id is not a safe identifier.")
    settings = _options(options)
    pdf_path, source = _source(pdf_path)
    identity = {"schema": CHECKPOINT_SCHEMA, "source": source, "options": settings,
                "enable_formula": True, "enable_table": True}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    directory = Path(job_dir).resolve() / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    checkpoint = directory / "checkpoint.json"
    state = {**identity, "request_fingerprint": fingerprint, "created_at": _now(),
             "status": "upload_required", "batch_id": None,
             "upload_state": "not_started", "progress": {"state": "upload_required"}}
    try:
        with _lock(directory / ".lock"):
            if checkpoint.is_file():
                try:
                    state = json.loads(checkpoint.read_text(encoding="utf-8"))
                except (ValueError, UnicodeError):
                    raise MinerUError("MinerU checkpoint is invalid; preserve it and use a separate job directory.") from None
                if not isinstance(state, dict) or state.get("request_fingerprint") != fingerprint:
                    raise MinerUError("MinerU checkpoint fingerprint does not match this request.")
                stored_batch = state.get("batch_id")
                if stored_batch and (not isinstance(stored_batch, str) or not _BATCH_ID.fullmatch(stored_batch)):
                    raise MinerUError("MinerU checkpoint has an invalid batch identifier.")
                if batch_id and stored_batch and batch_id != stored_batch:
                    raise MinerUError("A different MinerU batch already belongs to this request; use a separate job directory.")
            if batch_id and not state.get("batch_id"):
                state.update(batch_id=batch_id, status="pending", upload_state="external",
                             progress={"state": "pending"})
                state.pop("upload_url", None)
                _save(checkpoint, state)
            bundle = directory / "bundle.zip"
            if state.get("status") == "done" and bundle.is_file():
                expected = state.get("bundle_sha256")
                if expected and _sha(bundle) == expected and zipfile.is_zipfile(bundle):
                    return _result(state, checkpoint, cached=True)
                state.update(status="downloading", last_error="Cached archive is missing or invalid; reacquire from the same batch.")
                _save(checkpoint, state)
            if not state.get("batch_id") and state.get("status") in {"submitting", "submission_unknown"}:
                return _result(state, checkpoint, "submission_unknown",
                               "Submission outcome is unknown. Recover the batch ID from MinerU before adopting it; no repeat submission was made.")
            if not state.get("batch_id") and state.get("status") == "failed":
                return _result(state, checkpoint, message=state.get("last_error"))
            if not state.get("batch_id") and not allow_upload:
                _save(checkpoint, state)
                return _result(state, checkpoint, "upload_required", "Creating a MinerU task requires explicit upload permission.")
            if not checkpoint.is_file():
                _save(checkpoint, state)
            try:
                token, _ = _credential()
            except (OSError, UnicodeError, MinerUError) as exc:
                return _result(state, checkpoint, "credential_required", _safe(exc))
            if not token:
                return _result(state, checkpoint, "credential_required", "Set MINERU_TOKEN or the scalar token in ~/.mineru/config.yaml.")
            endpoint = settings["api_base"] + "/api/v4"
            if not state.get("batch_id"):
                # Persist before the non-idempotent POST. A timeout cannot silently
                # create another task on the next invocation.
                state.update(status="submitting", progress={"state": "submitting"})
                _save(checkpoint, state)
                payload = {"files": [{"name": "selection.pdf", "is_ocr": settings["ocr"], "data_id": fingerprint}],
                           "model_version": settings["model"], "language": settings["language"],
                           "enable_formula": True, "enable_table": True}
                try:
                    response = _api("POST", endpoint + "/file-urls/batch", token, payload)
                    new_batch = response.get("batch_id")
                    urls = response.get("file_urls")
                    if not isinstance(new_batch, str) or not _BATCH_ID.fullmatch(new_batch):
                        raise MinerUError("MinerU submission did not return a valid batch identifier.")
                    # Preserve a known batch ID even if its upload URL is malformed.
                    state.update(batch_id=new_batch, status="waiting-file", progress={"state": "waiting-file"})
                    _save(checkpoint, state)
                    if not isinstance(urls, list) or len(urls) != 1:
                        raise MinerUError("MinerU submission did not return exactly one upload URL.")
                    state["upload_url"] = _url(urls[0])
                    _save(checkpoint, state)
                except Exception as exc:
                    message = _safe(exc, token)
                    if state.get("batch_id"):
                        state["last_error"] = message
                        _save(checkpoint, state)
                        return _result(state, checkpoint, "error", message)
                    state.update(status="failed" if isinstance(exc, _APIError) else "submission_unknown", last_error=message)
                    _save(checkpoint, state)
                    return _result(state, checkpoint, message=message)
                state.update(upload_state="uploading", upload_attempts=1)
                _save(checkpoint, state)
                try:
                    _upload(pdf_path, state["upload_url"], source["sha256"])
                    state.update(upload_state="uploaded", status="pending", progress={"state": "pending"})
                    state.pop("upload_url", None)
                    state.pop("last_error", None)
                    _save(checkpoint, state)
                except Exception as exc:
                    message = _safe(exc, token)
                    state.update(upload_state="uncertain", last_error=message)
                    _save(checkpoint, state)
                    return _result(state, checkpoint, "error", message)
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    response = _api("GET", endpoint + "/extract-results/batch/" + state["batch_id"], token)
                    records = response.get("extract_result")
                    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
                        raise MinerUError("MinerU batch must contain exactly one extraction record for this derivative.")
                    record = records[0]
                    remote_status = record.get("state")
                    if remote_status not in {"done", "pending", "running", "failed", "waiting-file"}:
                        raise MinerUError("MinerU returned an unsupported task state.")
                    state.update(status=remote_status, progress=_progress(record, token))
                    state.pop("last_error", None)
                    if remote_status != "waiting-file":
                        state.pop("upload_url", None)
                        if state.get("upload_state") != "external":
                            state["upload_state"] = "uploaded"
                    _save(checkpoint, state)
                    if remote_status == "done":
                        state["status"] = "downloading"
                        _save(checkpoint, state)
                        _download(record.get("full_zip_url"), bundle)
                        state.update(status="done", bundle_sha256=_sha(bundle), bundle_bytes=bundle.stat().st_size)
                        _save(checkpoint, state)
                        return _result(state, checkpoint)
                    if remote_status == "failed":
                        return _result(state, checkpoint)
                    if remote_status == "waiting-file":
                        # First poll an uncertain PUT. A task already pending or
                        # running must never be uploaded again.
                        if allow_upload and state.get("upload_url"):
                            state.update(upload_state="uploading", upload_attempts=state.get("upload_attempts", 0) + 1)
                            _save(checkpoint, state)
                            try:
                                _upload(pdf_path, state["upload_url"], source["sha256"])
                            except Exception:
                                state["upload_state"] = "uncertain"
                                raise
                            state.update(upload_state="uploaded", status="pending", progress={"state": "pending"})
                            state.pop("upload_url", None)
                            _save(checkpoint, state)
                        else:
                            return _result(state, checkpoint, message="Batch is awaiting its file; no upload was performed.")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return _result(state, checkpoint)
                    time.sleep(min(5, remaining))
                except Exception as exc:
                    message = _safe(exc, token)
                    state["last_error"] = message
                    _save(checkpoint, state)
                    return _result(state, checkpoint, "error", message)
    except _Busy:
        return _result(state, checkpoint, "busy", "Another process holds this MinerU request; retry after it finishes.")
