"""Isolated MinerU 4.x boundary. No inference libraries are imported here.

The bundled wire schema is generated from MIT-licensed DocVortex 0.5.8.
See schemas/DocVortex-NOTICE.txt. Raw imports are immutable and content-addressed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping
import zipfile


class MinerUError(RuntimeError):
    """An actionable preparation error, never a request to use another backend."""


def sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def safe_relative(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or name.startswith('/')
            or any(p in ('', '.', '..') for p in name.split('/'))
            or any(p.endswith((' ', '.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p)
                   or any(ord(c) < 32 or c in '<>"|?*' for c in p) for p in path.parts)):
        raise ValueError(f'Unsafe relative member path: {name!r}')
    return path.as_posix()


def _run(args: list[str], *, env: Mapping[str, str], timeout: int = 120):
    return subprocess.run(args, env=dict(env), shell=False, capture_output=True,
                          text=True, encoding='utf8', errors='replace', timeout=timeout, check=True)


# Reading the effective config in MinerU's own interpreter avoids reproducing
# its YAML interpolation/defaults/environment precedence. Only safe fields leave it.
_PROBE = '''
import hashlib, importlib.metadata, json
from pathlib import Path
from mineru.config import config
d = config.model_dump(mode='json')
root = Path(config.model.base_dir)
features = config.llm_aided.features
print(json.dumps({
 'mineru_version': importlib.metadata.version('mineru'),
 'docvortex_version': importlib.metadata.version('docvortex'),
 'model_source': config.model.source,
 'vlm_server_url': bool(config.model.vlm.server_url),
 'llm_features_enabled': features.title_leveling or features.cross_page_table_cell_merge,
 'models_ready': root.is_dir() and any(p.is_file() for p in root.rglob('*')),
 'config_sha256': hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
}))
'''


def _environment(env: Mapping[str, str]) -> dict[str, str]:
    child = {**os.environ, **env}
    child.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    return child


def probe_mineru(python: Path, *, env: Mapping[str, str]) -> dict[str, Any]:
    if not Path(python).is_file():
        raise MinerUError('MinerU Python interpreter missing; set AINIEE_MINERU_PYTHON.')
    try:
        result = _run([str(python), '-B', '-c', _PROBE], env=_environment(env))
        data = json.loads(result.stdout.strip().splitlines()[-1])
        if not data['mineru_version'].startswith('4.') or data['docvortex_version'] != '0.5.8':
            raise ValueError('Unsupported MinerU/DocVortex version')
        return data
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
        raise MinerUError('MinerU Python/config probe failed; use MinerU 4.x with DocVortex 0.5.8 and check local configuration.') from exc


def validate_middle(document: dict) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise MinerUError('Install ainiee-translate[pdf] for PDF protocol validation.') from exc
    schema = json.loads(Path(__file__).with_name('schemas').joinpath('docvortex-middle-2.0.json').read_text(encoding='utf8'))
    errors = list(Draft202012Validator(schema).iter_errors(document))
    if errors:
        where = '/'.join(map(str, errors[0].absolute_path))
        raise ValueError(f'Invalid docvortex.middle/2.0 structure at {where}')
    page_ids = [p['page_idx'] for p in document['pages']]
    if page_ids != sorted(set(page_ids)):
        raise ValueError('Duplicate or unordered page indices')
    for page in document['pages']:
        indices = [b.get('index') for b in page['blocks']]
        if any(type(i) is not int for i in indices) or indices != sorted(set(indices)):
            raise ValueError('Top-level block indices must be unique and ordered')
        for block in page['blocks']:
            if document['metadata']['file_suffix'] in ('pdf', 'ofd') and block.get('bbox') is None:
                raise ValueError('Fixed-layout top-level block requires bbox')


def _image_refs(value: Any):
    if isinstance(value, dict):
        if value.get('image_url') or value.get('image_base64'):
            raise ValueError('A complete local bundle must materialize every image asset')
        if value.get('image_path'):
            yield safe_relative(value['image_path'])
        for child in value.values():
            yield from _image_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _image_refs(child)


def import_bundle(bundle: Path, destination: Path) -> dict[str, Any]:
    """Validate before committing anything; never replace a different import."""
    destination = Path(destination)
    bundle_hash = sha256(bundle)
    with zipfile.ZipFile(bundle) as archive:
        members = {}
        folded = set()
        total = 0
        for info in archive.infolist():
            name = safe_relative(info.orig_filename.rstrip('/'))
            if name.casefold() in folded:
                raise ValueError('Duplicate or case-colliding ZIP member')
            folded.add(name.casefold())
            if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ValueError('Unsupported ZIP member type')
            if info.is_dir():
                continue
            total += info.file_size
            if total > 2_000_000_000 or info.file_size > 256_000_000:
                raise ValueError('ZIP member exceeds import size limit')
            members[name] = info
        candidates = []
        for name in members:
            if name.endswith('.json'):
                try:
                    value = json.loads(archive.read(name))
                except (ValueError, UnicodeError):
                    continue
                if isinstance(value, dict) and value.get('schema') == 'docvortex.middle':
                    candidates.append((name, value))
        if len(candidates) != 1:
            raise ValueError('Bundle requires exactly one docvortex.middle/2.0 JSON')
        middle_path, document = candidates[0]
        validate_middle(document)
        assets = {}
        for reference in _image_refs(document):
            name = (PurePosixPath(middle_path).parent / reference).as_posix()
            if name not in members:
                raise ValueError(f'Missing image asset: {reference}')
            assets[name] = hashlib.sha256(archive.read(name)).hexdigest()
        hashes = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in members}
        manifest = dict(version=1, status='completed', schema='docvortex.middle', schema_version='2.0',
                        bundle_sha256=bundle_hash, middle_json=middle_path, assets=assets, files=hashes)
        if destination.exists():
            existing = destination / 'manifest.json'
            if not existing.is_file() or json.loads(existing.read_text(encoding='utf8')) != manifest:
                raise ValueError('Immutable import conflict: destination has different content')
            for name, expected in hashes.items():
                target = destination / name
                if target.is_symlink() or not target.is_file() or sha256(target) != expected:
                    raise ValueError('Immutable imported file changed')
            return manifest
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.import-', dir=destination.parent))
        try:
            for name in members:
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
            write_json(staging / 'manifest.json', manifest)
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return manifest


def extract_bundle(input_pdf: Path, destination: Path, *, python: Path,
                   env: Mapping[str, str], tier: str = 'standard') -> Path:
    if tier not in ('standard', 'basic', 'advanced', 'flash'):
        raise ValueError('Unknown MinerU tier')
    input_pdf = Path(input_pdf).resolve()
    child_env = _environment(env)
    probe = probe_mineru(python, env=child_env)
    if probe['model_source'] != 'local' or probe['vlm_server_url'] or probe['llm_features_enabled']:
        raise MinerUError('Local preflight rejected config: require model.source=local, no VLM server URL and disabled LLM features. Original config was not changed.')
    if not probe['models_ready']:
        raise MinerUError('Local models missing; prepare MinerU models explicitly before retrying.')
    fingerprint = dict(input_sha256=sha256(input_pdf), tier=tier, probe=probe,
                       interpreter=str(Path(python).resolve()))
    run = Path(destination) / digest(fingerprint)
    manifest_path = run / 'manifest.json'
    output = run / 'result.zip'
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding='utf8'))
        if previous.get('status') == 'completed' and output.is_file() and sha256(output) == previous.get('bundle_sha256'):
            import_bundle(output, run / 'raw')
            return output
    run.mkdir(parents=True, exist_ok=True)
    manifest = dict(version=1, **fingerprint, status='running')
    write_json(manifest_path, manifest)
    args = [str(python), '-B', '-m', 'mineru.kit.main', 'parse', str(input_pdf),
            '-o', str(output.resolve()), '--format', 'zip', '--tier', tier]
    try:
        result = _run(args, env=child_env, timeout=3600)
        if result.returncode:
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        imported = import_bundle(output, run / 'raw')
        manifest.update(status='completed', bundle_sha256=imported['bundle_sha256'],
                        schema=imported['schema'], schema_version=imported['schema_version'], assets=imported['assets'])
        write_json(manifest_path, manifest)
        return output
    except BaseException as exc:
        manifest['status'] = 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed'
        manifest['error_type'] = type(exc).__name__
        # Logs are private; still redact inherited credentials before recording.
        detail = str(getattr(exc, 'stderr', '') or str(exc))
        for key, value in child_env.items():
            if value and any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')):
                detail = detail.replace(value, '[redacted]')
        (run / 'diagnostic.log').write_text(detail, encoding='utf8')
        write_json(manifest_path, manifest)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise MinerUError(f'Local MinerU extraction failed; diagnostics: {run / "diagnostic.log"}. Retry the same command after resolving the cause.') from exc
