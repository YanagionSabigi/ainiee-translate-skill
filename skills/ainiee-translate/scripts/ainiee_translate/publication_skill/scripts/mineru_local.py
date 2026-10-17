"""Reusable, durable acquisition of a *local* MinerU structured result.

``ensure_bundle(pdf_path, job_dir, options, cancel_event=None)`` accepts an original
local PDF and one-based physical ``pages`` (a sequence of integers).  It returns
only paths, hashes, state, page numbers and counts; document content and CLI output
stay in files.  It does not import, transform or assess document correctness.

Options: ``install_root``, ``cli``, ``config``, ``environment_script``, ``tier``
(standard/advanced), ``pages``, ``format`` (zip), ``timeout`` (seconds; None means
unlimited), and ``language`` (recorded as a hint; MinerU 4.0.10 has no language CLI
option).  No arbitrary CLI arguments or remote fallback are accepted. Completed
ZIPs are reused only after their SHA-256 and their request fingerprint match.

On Windows every subprocess starts suspended, is assigned to a private Job Object
with KILL_ON_JOB_CLOSE, then resumes. Its entire job is terminated and checked on
success, failure, timeout and cancellation. Other MinerU instances are untouched.
The deployment config is copied into the job directory and MinerU itself checks
its effective settings, including environment overrides. Global config is never
changed. Runtime logs may contain private document data: inspect them locally.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

CHECKPOINT_SCHEMA = "mineru-local-acquisition/1"
RUNNER_VERSION = "1"
MAX_MIDDLE_JSON_BYTES = 536_870_912
MAX_ZIP_BYTES = 4_294_967_296


class LocalMinerUError(ValueError):
    """A fixed, content-free diagnostic; CLI details remain in local logs."""

    def __init__(self, code, message=None):
        self.code = str(code)
        super().__init__(message or f"Local MinerU check failed ({self.code}); inspect the saved local logs.")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp." + uuid.uuid4().hex)
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(path):
    """OS-held lock; a crashed owner cannot leave a stale lock behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
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
        except OSError:
            raise LocalMinerUError("checkpoint_locked") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _timeout(value):
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise LocalMinerUError("invalid_timeout") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise LocalMinerUError("invalid_timeout")
    return seconds


def _cancelled(event):
    return event is not None and event.is_set()


def _windows_process(command, *, cwd, env, log_path, timeout, cancel_event):
    """CreateProcessW rather than Popen: Popen closes the primary thread early."""
    import ctypes
    import msvcrt
    from ctypes import wintypes as w

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR),
                    ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD), ("dwYSize", w.DWORD),
                    ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
                    ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
                    ("lpReserved2", ctypes.POINTER(w.BYTE)), ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE)]

    class PROCESSINFO(ctypes.Structure):
        _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE), ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]

    class BASICLIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ULONG_PTR), ("MaximumWorkingSetSize", ULONG_PTR),
                    ("ActiveProcessLimit", w.DWORD), ("Affinity", ULONG_PTR), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

    class IOCOUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDEDLIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASICLIMIT), ("IoInfo", IOCOUNTERS), ("ProcessMemoryLimit", ULONG_PTR),
                    ("JobMemoryLimit", ULONG_PTR), ("PeakProcessMemoryUsed", ULONG_PTR), ("PeakJobMemoryUsed", ULONG_PTR)]

    class ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64), ("ThisPeriodTotalUserTime", ctypes.c_int64),
                    ("ThisPeriodTotalKernelTime", ctypes.c_int64), ("TotalPageFaultCount", w.DWORD),
                    ("TotalProcesses", w.DWORD), ("ActiveProcesses", w.DWORD), ("TotalTerminatedProcesses", w.DWORD)]

    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD, ctypes.c_void_p,
                                     w.LPCWSTR, ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESSINFO)]
    kernel.CreateProcessW.restype = w.BOOL
    kernel.ResumeThread.argtypes = [w.HANDLE]
    kernel.ResumeThread.restype = w.DWORD
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    kernel.GetExitCodeProcess.restype = w.BOOL
    kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    kernel.TerminateJobObject.restype = w.BOOL
    kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    kernel.TerminateProcess.restype = w.BOOL
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
    kernel.QueryInformationJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise LocalMinerUError("process_job_create_failed")
    process = PROCESSINFO()
    assigned = False
    started = time.monotonic()
    exit_code = None
    status = "failed"
    cleanup_verified = False
    interrupted = False
    try:
        limits = EXTENDEDLIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise LocalMinerUError("process_job_config_failed")
        with Path(log_path).open("ab", buffering=0) as log, open(os.devnull, "rb", buffering=0) as null:
            os.set_inheritable(log.fileno(), True)
            os.set_inheritable(null.fileno(), True)
            startup = STARTUPINFO()
            startup.cb = ctypes.sizeof(startup)
            startup.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
            startup.hStdInput = msvcrt.get_osfhandle(null.fileno())
            startup.hStdOutput = startup.hStdError = msvcrt.get_osfhandle(log.fileno())
            env_text = "\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda x: x[0].upper())) + "\0\0"
            env_buffer = ctypes.create_unicode_buffer(env_text)
            command_buffer = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(item) for item in command]))
            flags = 0x00000004 | 0x08000000 | 0x00000400  # suspended, hidden, Unicode env
            try:
                if not kernel.CreateProcessW(str(command[0]), command_buffer, None, None, True, flags, env_buffer,
                                             str(cwd), ctypes.byref(startup), ctypes.byref(process)):
                    raise LocalMinerUError("process_start_failed")
            finally:
                os.set_inheritable(log.fileno(), False)
                os.set_inheritable(null.fileno(), False)
            if not kernel.AssignProcessToJobObject(job, process.hProcess):
                # The primary thread is still suspended: no uncontrolled descendants exist.
                raise LocalMinerUError("process_job_assign_failed")
            assigned = True
            if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
                raise LocalMinerUError("process_resume_failed")
            while True:
                wait_result = kernel.WaitForSingleObject(process.hProcess, 100)
                if wait_result == 0:
                    code = w.DWORD()
                    if not kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code)):
                        raise LocalMinerUError("process_exit_check_failed")
                    exit_code = int(code.value)
                    status = "done" if exit_code == 0 else "failed"
                    break
                if wait_result == 0xFFFFFFFF:
                    raise LocalMinerUError("process_wait_failed")
                if _cancelled(cancel_event):
                    status = "cancelled"
                    break
                if timeout is not None and time.monotonic() - started >= timeout:
                    status = "timeout"
                    break
    except KeyboardInterrupt:
        status = "cancelled"
        interrupted = True
    finally:
        if process.hProcess:
            if assigned:
                # Also removes a worker that outlives a successfully exited CLI.
                kernel.TerminateJobObject(job, 1)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    accounting = ACCOUNTING()
                    if kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                        if accounting.ActiveProcesses == 0:
                            cleanup_verified = True
                            break
                    time.sleep(0.05)
            else:
                kernel.TerminateProcess(process.hProcess, 1)
                cleanup_verified = kernel.WaitForSingleObject(process.hProcess, 10000) == 0
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
        else:
            cleanup_verified = True
        kernel.CloseHandle(job)  # kill-on-close remains the final resource safety net
    return {"status": status, "exit_code": exit_code, "pid": int(process.dwProcessId),
            "cleanup_verified": cleanup_verified, "elapsed_seconds": round(time.monotonic() - started, 3),
            "keyboard_interrupt": interrupted}


def run_owned_process(command, *, cwd, env, log_path, timeout=3600, cancel_event=None):
    """Run a dedicated process tree and write all stdout/stderr to ``log_path``.

    Result keys: status (done/failed/cancelled/timeout), exit_code, pid,
    cleanup_verified, elapsed_seconds, keyboard_interrupt. A cleanup failure must
    never be considered a successful acquisition. This primitive is reusable for
    another local MinerU skill; the caller supplies a *local* command and env.
    """
    command = [str(item) for item in command]
    if not command or not Path(command[0]).is_file():
        raise LocalMinerUError("process_executable_missing")
    timeout = _timeout(timeout)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    if _cancelled(cancel_event):
        return {"status": "cancelled", "exit_code": None, "pid": None, "cleanup_verified": True, "elapsed_seconds": 0, "keyboard_interrupt": False}
    if os.name == "nt":
        return _windows_process(command, cwd=cwd, env=env, log_path=log_path, timeout=timeout, cancel_event=cancel_event)
    started = time.monotonic()
    process = None
    status = "failed"
    interrupted = False
    cleanup_verified = False
    try:
        with Path(log_path).open("ab") as log:
            process = subprocess.Popen(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            while process.poll() is None:
                if _cancelled(cancel_event):
                    status = "cancelled"
                    break
                if timeout is not None and time.monotonic() - started >= timeout:
                    status = "timeout"
                    break
                time.sleep(0.1)
            else:
                status = "done" if process.returncode == 0 else "failed"
    except KeyboardInterrupt:
        status, interrupted = "cancelled", True
    except OSError:
        raise LocalMinerUError("process_start_failed") from None
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
            cleanup_verified = True
    return {"status": status, "exit_code": process.returncode if process else None, "pid": process.pid if process else None,
            "cleanup_verified": cleanup_verified, "elapsed_seconds": round(time.monotonic() - started, 3), "keyboard_interrupt": interrupted}


# Run in the deployment's interpreter. Only safety flags/hashes/counts are emitted
# to a private JSON file; exceptions and import logs are redirected to disk.
_CONFIG_PROBE = r'''
import hashlib, importlib.metadata, json, os, pathlib, sys
try:
    from mineru.config import config, get_config_file_path
    data = config.model_dump(mode="json")
    base = pathlib.Path(config.model.base_dir).expanduser().resolve()
    manifest = []
    file_count = 0
    for path in sorted(base.rglob("*")):
        if path.is_file():
            stat = path.stat()
            entry = [path.relative_to(base).as_posix(), stat.st_size, stat.st_mtime_ns]
            if path.suffix.lower() in {".json", ".yaml", ".yml", ".txt"} and stat.st_size <= 1048576:
                entry.append(hashlib.sha256(path.read_bytes()).hexdigest())
            manifest.append(entry)
            file_count += 1
    result = {"status":"checked", "model_source":config.model.source,
              "vlm_server_url_empty": not bool(config.model.vlm.server_url.strip()),
              "llm_title_leveling":config.llm_aided.features.title_leveling,
              "llm_cross_page_table_cell_merge":config.llm_aided.features.cross_page_table_cell_merge,
              "small_backend":config.model.small_backend, "vlm_engine":config.model.vlm.engine,
              "model_base_dir":str(base), "model_directory_exists":base.is_dir(), "model_file_count":file_count,
              "model_identity_sha256":hashlib.sha256(json.dumps(manifest,separators=(",",":"),ensure_ascii=False).encode()).hexdigest(),
              "effective_config_sha256":hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest(),
              "effective_config_path":str(pathlib.Path(get_config_file_path()).resolve()),
              "version":importlib.metadata.version("mineru"), "python_version":sys.version.split()[0]}
except Exception:
    import traceback
    traceback.print_exc()  # redirected to the private local config-probe.log
    result = {"status":"invalid_config"}
pathlib.Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
sys.exit(0 if result["status"] == "checked" else 3)
'''

_ENV_SNAPSHOT = r'''
param([string]$EnvironmentScript, [string]$SnapshotPath)
$ErrorActionPreference = 'Stop'
. $EnvironmentScript
$Snapshot = @{}
Get-ChildItem Env: | Where-Object { $_.Name -match '^(MINERU_|HF_|HUGGINGFACE_|MODELSCOPE_|TORCH_|XDG_|UV_|PYTHON|GRADIO_|TEMP$|TMP$)' } | ForEach-Object { $Snapshot[$_.Name] = $_.Value }
$Snapshot | ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $SnapshotPath -Encoding utf8
'''


def validate_local_settings(summary):
    """Reject unsafe *effective* MinerU settings; return content-free checks.

    ``summary`` is the deployment probe result. Required keys: status=checked,
    model_source=local, vlm_server_url_empty=True, llm_title_leveling=False,
    llm_cross_page_table_cell_merge=False, model_directory_exists=True,
    model_file_count>0. Boolean fields must actually be booleans.
    """
    if summary.get("status") != "checked":
        raise LocalMinerUError("effective_config_invalid")
    if summary.get("model_source") != "local":
        raise LocalMinerUError("model_source_not_local")
    if summary.get("vlm_server_url_empty") is not True:
        raise LocalMinerUError("remote_vlm_forbidden")
    if summary.get("llm_title_leveling") is not False or summary.get("llm_cross_page_table_cell_merge") is not False:
        raise LocalMinerUError("llm_postprocessing_forbidden")
    if summary.get("model_directory_exists") is not True or not isinstance(summary.get("model_file_count"), int) or summary["model_file_count"] <= 0:
        raise LocalMinerUError("local_models_missing")
    return {"model_source_local": True, "remote_vlm_disabled": True, "llm_postprocessing_disabled": True, "models_present": True}


def _local_path(raw, *, must_exist=True):
    path = Path(raw).expanduser().resolve()
    if str(path).startswith(("\\\\", "//")):
        raise LocalMinerUError("network_path_forbidden")
    if must_exist and not path.exists():
        raise LocalMinerUError("local_path_missing")
    return path


def inspect_deployment(options=None, job_dir=None, cancel_event=None):
    """Prepare a private runtime and verify MinerU's actual effective config.

    Returns deployment metadata plus a process environment for ``ensure_bundle``.
    Environment values may contain credentials: never print or serialize this
    internal return value. ``probe`` is the safe user-facing inspection API.
    """
    options = dict(options or {})
    configured_root = options.get("install_root") or os.environ.get("AINIEE_MINERU_ROOT")
    if not configured_root:
        raise LocalMinerUError("local_install_root_required",
                              "Set AINIEE_MINERU_ROOT or pass --mineru-local-root before local extraction.")
    root = _local_path(configured_root)
    cli = _local_path(options.get("cli") or root / ".venv" / "Scripts" / "mineru-kit.exe")
    interpreter = _local_path(cli.parent / ("python.exe" if os.name == "nt" else "python"))
    environment_script = _local_path(options.get("environment_script") or root / "Set-MinerUEnvironment.ps1")
    runtime = _local_path(job_dir or Path.cwd() / "mineru-local-probe", must_exist=False) / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    snapshot = runtime / ("environment." + uuid.uuid4().hex + ".json")
    script = runtime / "capture-environment.ps1"
    script.write_text(_ENV_SNAPSHOT, encoding="utf-8-sig")
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        raise LocalMinerUError("powershell_missing")
    try:
        result = run_owned_process([powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script,
                                    str(environment_script), str(snapshot)], cwd=runtime, env=env,
                                   log_path=runtime / "environment.log", timeout=60, cancel_event=cancel_event)
        if result["status"] != "done" or not result["cleanup_verified"] or not snapshot.is_file():
            raise LocalMinerUError("environment_setup_" + result["status"])
        try:
            values = json.loads(snapshot.read_text(encoding="utf-8-sig"))
            if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()):
                raise ValueError
            env.update(values)
        except (ValueError, OSError):
            raise LocalMinerUError("environment_snapshot_invalid") from None
    finally:
        snapshot.unlink(missing_ok=True)  # may include inherited credentials
    config_path = _local_path(options.get("config") or env.get("MINERU_CONFIG") or root / "state" / "config.yaml")
    config_sha = _sha(config_path)
    isolated_config = runtime / "config.yaml"
    config_bytes = config_path.read_bytes()
    if hashlib.sha256(config_bytes).hexdigest() != config_sha:
        raise LocalMinerUError("config_changed_during_probe")
    isolated_config.write_bytes(config_bytes)
    env["MINERU_CONFIG"] = str(isolated_config)
    env["MINERU_HOME"] = str(runtime / "state")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["MODELSCOPE_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["GRADIO_ANALYTICS_ENABLED"] = "False"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TEMP"] = env["TMP"] = str(runtime / "tmp")
    for directory in (runtime / "state", runtime / "tmp"):
        directory.mkdir(parents=True, exist_ok=True)
    # Direct local_parse never uses these, but reject unintended inherited service
    # endpoints rather than carrying them into the dedicated extraction process.
    if any(env.get(name, "").strip() for name in ("MINERU_API_URL", "MINERU_REMOTE_URL", "MINERU_VLM_SERVER_URL")):
        raise LocalMinerUError("remote_environment_forbidden")
    probe_path = runtime / "effective-local-settings.json"
    probe_script = runtime / "inspect-effective-config.py"
    probe_script.write_text(_CONFIG_PROBE, encoding="utf-8")
    result = run_owned_process([interpreter, str(probe_script), str(probe_path)], cwd=runtime, env=env,
                               log_path=runtime / "config-probe.log", timeout=120, cancel_event=cancel_event)
    if result["status"] != "done" or not result["cleanup_verified"] or not probe_path.is_file():
        raise LocalMinerUError("config_probe_" + result["status"])
    try:
        summary = json.loads(probe_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise LocalMinerUError("config_probe_invalid") from None
    checks = validate_local_settings(summary)
    _local_path(summary["model_base_dir"])
    if Path(summary["effective_config_path"]).resolve() != isolated_config.resolve():
        raise LocalMinerUError("effective_config_path_mismatch")
    relevant_env = {key: value for key, value in env.items()
                    if key in {"PATH", "PATHEXT", "VIRTUAL_ENV"}
                    or re.match(r"^(MINERU_|HF_|HUGGINGFACE_|MODELSCOPE_|TORCH_|XDG_|UV_|PYTHON|GRADIO_|CUDA_|CUBLAS_|OMP_|MKL_|VLLM_|LMDEPLOY_|TRANSFORMERS_|TOKENIZERS_)", key)}
    return {"env": env, "cli": cli, "interpreter": interpreter, "root": root, "config": config_path,
            "isolated_config": isolated_config, "runtime": runtime, "checks": checks, "summary": summary,
            "identity": {"runner_version": RUNNER_VERSION, "cli_sha256": _sha(cli), "cli_path": str(cli),
                         "mineru_version": summary["version"], "python_version": summary["python_version"],
                         "config_sha256": config_sha, "effective_config_sha256": summary["effective_config_sha256"],
                         "environment_script_sha256": _sha(environment_script), "environment_sha256": _json_sha(relevant_env),
                         "model_identity_sha256": summary["model_identity_sha256"], "model_file_count": summary["model_file_count"]}}


def probe(options=None):
    """Nonthrowing, content-free installation check for backend discovery."""
    try:
        with tempfile.TemporaryDirectory(prefix="mineru-local-probe-") as directory:
            deployment = inspect_deployment(options, directory)
            return {"available": True, "status": "checked", "version": deployment["summary"]["version"],
                    "model_file_count": deployment["summary"]["model_file_count"], **deployment["checks"],
                    "process_tree_isolation": "windows-job-object" if os.name == "nt" else "process-group",
                    "document_content_in_console": False}
    except LocalMinerUError as exc:
        return {"available": False, "status": "unavailable", "error_code": exc.code, "document_content_in_console": False}
    except (OSError, ValueError):
        return {"available": False, "status": "unavailable", "error_code": "local_probe_failed", "document_content_in_console": False}


def _pages(raw):
    if raw is None or raw == "all":
        return None
    if isinstance(raw, str):
        pages = []
        for part in raw.split(","):
            match = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", part)
            if not match:
                raise LocalMinerUError("invalid_pages")
            first, last = int(match[1]), int(match[2] or match[1])
            if last < first or last - first > 1_000_000:
                raise LocalMinerUError("invalid_pages")
            pages.extend(range(first, last + 1))
    elif isinstance(raw, Sequence):
        pages = list(raw)
    else:
        raise LocalMinerUError("invalid_pages")
    if not pages or any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in pages):
        raise LocalMinerUError("invalid_pages")
    return sorted(set(pages))


def inspect_bundle(path, expected_pages=None):
    """Check ZIP structure/source indices and return counts, never content."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_ZIP_BYTES:
        raise LocalMinerUError("structured_bundle_missing_or_large")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len({entry.filename for entry in entries}) != len(entries):
                raise LocalMinerUError("duplicate_bundle_paths")
            for entry in entries:
                normalized = entry.filename.replace("\\", "/")
                if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in normalized.split("/") or entry.flag_bits & 1:
                    raise LocalMinerUError("unsafe_bundle_paths")
            candidates = [entry for entry in entries if Path(entry.filename).name in {"middle_json.json", "middle.json"} or Path(entry.filename).name.endswith("_middle.json")]
            if len(candidates) != 1 or candidates[0].file_size > MAX_MIDDLE_JSON_BYTES:
                raise LocalMinerUError("middle_json_missing_or_ambiguous")
            data = json.loads(archive.read(candidates[0]))
            if not isinstance(data, dict) or data.get("schema") != "docvortex.middle" or data.get("schema_version") != "2.0" or not isinstance(data.get("pages"), list):
                raise LocalMinerUError("unsupported_middle_schema")
            indices = [page.get("page_idx") if isinstance(page, dict) else None for page in data["pages"]]
            if not indices or any(isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in indices) or indices != sorted(set(indices)):
                raise LocalMinerUError("invalid_source_page_indices")
            page_numbers = [index + 1 for index in indices]
            if expected_pages is not None and page_numbers != list(expected_pages):
                raise LocalMinerUError("source_page_mapping_mismatch")
            # Avoid inflating every asset; ZIP CRC integrity is checked on merge/import.
            return {"schema": "docvortex.middle/2.0", "page_count": len(indices), "pages": page_numbers,
                    "resource_count": sum(1 for entry in entries if not entry.is_dir() and entry != candidates[0]),
                    "archive_entry_count": len(entries), "source_indices_preserved": True}
    except LocalMinerUError:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError):
        raise LocalMinerUError("structured_bundle_invalid") from None


def _result(state, checkpoint, *, cached=False):
    last = (state.get("attempts") or [{}])[-1]
    return {"status": state["status"], "bundle": Path(state["bundle"]) if state.get("status") == "done" else None,
            "checkpoint": Path(checkpoint), "request_fingerprint": state.get("request_fingerprint"),
            "fingerprint": state.get("request_fingerprint"), "cached": cached,
            "progress": state.get("progress", {}), "error_code": state.get("error_code"),
            "log": Path(last["log"]) if last.get("log") else None,
            "process": last.get("process", {})}


def ensure_bundle(pdf_path, job_dir, options=None, cancel_event=None):
    """Acquire or reuse one local structured ZIP; never downgrade or use cloud.

    Failure/timeout/cancellation returns a durable state and a content-free code.
    Bad inputs or unsafe deployment settings raise ``LocalMinerUError``. Each
    attempt remains in ``requests/<fingerprint>/attempts/<id>``; interrupted checkpoints are retained
    and a later call creates a new attempt. Callers handle batching/page mapping.
    """
    options = dict(options or {})
    if set(options) - {"install_root", "cli", "config", "environment_script", "tier", "pages", "format", "timeout", "language"}:
        raise LocalMinerUError("unsupported_local_option")
    tier = options.get("tier") or "standard"
    if tier not in {"standard", "advanced"}:
        raise LocalMinerUError("invalid_local_tier")
    if options.get("format", "zip") != "zip":
        raise LocalMinerUError("structured_zip_required")
    pages = _pages(options.get("pages"))
    timeout = _timeout(options.get("timeout", 3600))
    pdf = _local_path(pdf_path)
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        raise LocalMinerUError("local_pdf_required")
    job = _local_path(job_dir, must_exist=False)
    job.mkdir(parents=True, exist_ok=True)
    with _lock(job / "checkpoint.lock"):
        # A shared job root may serve many batches/tiers. Never replace another
        # request's checkpoint: completed A remains reusable after B has run.
        preflight_path = job / "preflight.json"
        if preflight_path.is_file():
            try:
                preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
                if not isinstance(preflight, dict) or not isinstance(preflight.get("attempts"), list):
                    raise ValueError
            except (ValueError, OSError):
                raise LocalMinerUError("preflight_checkpoint_invalid") from None
        else:
            preflight = {"schema": "mineru-local-preflight/1", "attempts": []}
        preflight_attempt = {"started_at": _now(), "status": "checking", "tier": tier, "pages": pages}
        preflight["attempts"].append(preflight_attempt)
        _save(preflight_path, preflight)
        try:
            deployment = inspect_deployment(options, job, cancel_event)
        except LocalMinerUError as exc:
            preflight_attempt.update({"status": "failed", "error_code": exc.code, "finished_at": _now()})
            _save(preflight_path, preflight)
            raise
        except KeyboardInterrupt:
            preflight_attempt.update({"status": "cancelled", "error_code": "local_preflight_cancelled", "finished_at": _now()})
            _save(preflight_path, preflight)
            raise LocalMinerUError("local_preflight_cancelled") from None
        except (OSError, ValueError):
            preflight_attempt.update({"status": "failed", "error_code": "local_preflight_failed", "finished_at": _now()})
            _save(preflight_path, preflight)
            raise LocalMinerUError("local_preflight_failed") from None
        preflight_attempt.update({"status": "checked", "finished_at": _now(), "checks": deployment["checks"]})
        _save(preflight_path, preflight)
        source_sha = _sha(pdf)
        request = {"source_sha256": source_sha, "source_bytes": pdf.stat().st_size, "tier": tier, "pages": pages,
                   "format": "zip", "language_hint": options.get("language"), "ocr_mode": "auto",
                   "deployment": deployment["identity"]}
        fingerprint = _json_sha(request)
        request_dir = job / "requests" / fingerprint
        request_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = request_dir / "checkpoint.json"
        if checkpoint.is_file():
            try:
                state = json.loads(checkpoint.read_text(encoding="utf-8"))
                if not isinstance(state, dict) or state.get("schema") != CHECKPOINT_SCHEMA or not isinstance(state.get("attempts"), list):
                    raise ValueError
            except (ValueError, OSError):
                raise LocalMinerUError("checkpoint_invalid") from None
        else:
            state = {"schema": CHECKPOINT_SCHEMA, "created_at": _now(), "status": "new", "attempts": []}
        if state.get("status") == "done" and state.get("request_fingerprint") == fingerprint:
            cached_path = Path(state.get("bundle", ""))
            try:
                cached_path.resolve().relative_to(request_dir.resolve())
                if cached_path.is_file() and _sha(cached_path) == state.get("bundle_sha256"):
                    state["progress"] = inspect_bundle(cached_path, pages)
                    return _result(state, checkpoint, cached=True)
            except (ValueError, OSError, LocalMinerUError):
                pass
            state["attempts"].append({"status": "cache_rejected", "at": _now(), "request_fingerprint": fingerprint, "error_code": "cached_artifact_invalid"})
        if state.get("status") == "running" and state["attempts"]:
            state["attempts"][-1]["status"] = "interrupted"
            state["attempts"][-1]["finished_at"] = _now()
        attempt_id = _now().replace(":", "").replace("-", "") + "-" + uuid.uuid4().hex[:10]
        attempt_dir = request_dir / "attempts" / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=True)
        bundle = attempt_dir / "result.zip"
        log = attempt_dir / "mineru.log"
        attempt = {"id": attempt_id, "status": "running", "started_at": _now(), "tier": tier, "pages": pages,
                   "request_fingerprint": fingerprint, "log": str(log), "bundle": str(bundle)}
        state.update({"status": "running", "request_fingerprint": fingerprint, "request": request,
                      "bundle": str(bundle), "error_code": None, "progress": {"requested_page_count": len(pages) if pages else None}})
        state["attempts"].append(attempt)
        state["updated_at"] = _now()
        _save(checkpoint, state)
        command = [deployment["cli"], "parse", pdf, "--tier", tier, "--format", "zip", "--pages",
                   ",".join(map(str, pages)) if pages else "all", "--output", bundle]
        try:
            process = run_owned_process(command, cwd=deployment["runtime"], env=deployment["env"], log_path=log,
                                        timeout=timeout, cancel_event=cancel_event)
            attempt["process"] = process
            state["status"] = process["status"]
            if not process["cleanup_verified"]:
                raise LocalMinerUError("process_cleanup_unverified")
            if state["status"] == "done":
                if _sha(pdf) != source_sha or _sha(deployment["config"]) != deployment["identity"]["config_sha256"]:
                    raise LocalMinerUError("input_changed_during_extraction")
                state["progress"] = inspect_bundle(bundle, pages)
                state["bundle_sha256"] = _sha(bundle)
                if options.get("language"):
                    state["progress"]["language_hint_cli_supported"] = False
            else:
                state["error_code"] = "local_parse_" + state["status"]
        except LocalMinerUError as exc:
            state["status"], state["error_code"] = "failed", exc.code
        except KeyboardInterrupt:
            state["status"], state["error_code"] = "cancelled", "local_parse_cancelled"
        except (OSError, ValueError):
            state["status"], state["error_code"] = "failed", "local_acquisition_failed"
        finally:
            attempt["status"] = state["status"]
            attempt["error_code"] = state.get("error_code")
            attempt["finished_at"] = state["updated_at"] = _now()
            _save(checkpoint, state)
        return _result(state, checkpoint)
