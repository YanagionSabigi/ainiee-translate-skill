"""Reusable translation modules with Chinese editable files and legacy read support.

New modules live in 翻译预设/翻译模组 under AINIEE_TRANSLATE_HOME.
Loading maps user files to the existing project runtime filenames and freezes
preset choices into that project without rewriting the source module.
"""
import argparse
import json
import os
import shutil
import time
from pathlib import Path
import re

from . import helpers
from . import glossary_document as gd

SCHEMA_VERSION = 1

# Module-relative filenames (the on-disk schema), defined once to avoid drift
# between write_module_json (which records them) and load_module (which copies them).
TRANSLATE_PROMPT = "初次翻译.md"
POLISH_PROMPT = "润色校对.md"
GLOSSARY_LOCKED = "glossary.locked.json"
GLOSSARY_SCHEMA = "glossary.locked.schema.json"
SETTINGS = "预设参数.md"
STYLE = "语言风格.md"
LEGACY_FILES = {TRANSLATE_PROMPT: 'translate_prompt.md',
                POLISH_PROMPT: 'polish_prompt.md', STYLE: 'style.md'}
EXAMPLES = "examples.json"
# Name the translate step consumes inside a project's work/ dir
WORK_USER_PROMPT = "user_prompt.md"


def home() -> str:
    return os.environ.get("AINIEE_TRANSLATE_HOME", os.path.expanduser("~/.ainiee-translate"))


def modules_root() -> str:
    return os.path.join(home(), "翻译预设", "翻译模组")


def module_dir(name: str) -> str:
    if not name.strip() or name in ('.', '..') or any(c in name for c in '/\\:'):
        raise ValueError('模组名须为单个文件夹名称')
    current = os.path.join(modules_root(), name)
    legacy = os.path.join(home(), 'modules', name)
    return current if os.path.isdir(current) or not os.path.isdir(legacy) else legacy


def _source(d, filename):
    current = os.path.join(d, filename)
    return current if os.path.isfile(current) else os.path.join(d, LEGACY_FILES.get(filename, filename))


def _settings(d):
    path = Path(d) / SETTINGS
    if not path.exists():
        return {}
    text = path.read_text(encoding='utf8')
    result = {}
    for label, key, choices in [('标点符号模式', 'punctuation_mode', ('full', 'half')),
                                ('人名翻译模式', 'person_name_mode', tuple('ABCD'))]:
        values = re.findall(r'^- ' + label + r'：([^\s]+)\s*$', text, re.M)
        if len(values) != 1 or values[0] not in choices:
            raise ValueError(f'{SETTINGS} 中 {label} 必须明确填写一个有效值')
        result[key] = values[0]
    return result


def _read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def list_modules() -> list[dict]:
    active = (_read_json(os.path.join(home(), "active.json"), {}) or {}).get("active_module")
    out = []
    seen = set()
    for root in (modules_root(), os.path.join(home(), 'modules')):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if name in seen:
                continue
            mj = _read_json(os.path.join(root, name, "module.json"))
            if mj is None:
                continue
            seen.add(name)
            out.append({"name": name, "title": mj.get("title", name),
                        "source_language": mj.get("source_language", ""),
                        "target_language": mj.get("target_language", ""),
                        "has_polish": os.path.exists(_source(os.path.join(root, name), POLISH_PROMPT)),
                        "active": name == active, **{k: v for k, v in show_module(name).items() if k not in ("name", "module", "files")}})
    return out


def show_module(name: str) -> dict:
    d = module_dir(name)
    if not os.path.isdir(d):
        raise FileNotFoundError(f"module not found: {name}")
    mj = _read_json(os.path.join(d, "module.json"), {}) or {}
    locked = _read_json(os.path.join(d, GLOSSARY_LOCKED), {}) or {}
    extra = {}
    if gd.structured(locked):
        gd.validate_document(locked)
        extra = dict(glossary_format=locked['schema_version'], persons=len(locked['persons']),
                     terminology=len(locked['terminology']), abbreviations=len(locked['abbreviations']),
                     categories=len(locked['categories']), person_name_mode=gd.read_policy(os.path.join(d, GLOSSARY_LOCKED), locked)['person_name_mode'])
    files = sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
    return {"name": name, "module": mj, "files": files,
            "terms": len(locked.get("terms", [])),
            "characters": len(locked.get("characters", [])),
            "non_translate": len(locked.get("non_translate", [])), **extra, **_settings(d)}


def create_module(name: str, source_language="", target_language="", title="", *, name_mode="D", punctuation_mode="full", categories=None, category_ids=None) -> str:
    d = module_dir(name)
    if punctuation_mode not in ('full', 'half'):
        raise ValueError('标点符号模式须为 full 或 half')
    document = gd.empty_document()
    if categories is not None:
        if isinstance(categories, (str, os.PathLike)):
            with open(categories, encoding='utf8') as stream:
                categories = json.load(stream)
        if isinstance(categories, dict) and set(categories) != {'categories'}:
            raise ValueError('Categories import must be an array or an object with only categories')
        document['categories'] = categories['categories'] if isinstance(categories, dict) else categories
    policy = dict(schema_version='1.0.0', person_name_mode=name_mode)
    if category_ids: policy['category_ids'] = list(category_ids)
    gd.validate_document(document)
    gd.runtime_view(document, policy)
    if os.path.exists(os.path.join(d, 'module.json')):
        existing = gd.read_document(os.path.join(d, GLOSSARY_LOCKED))
        mj = _read_json(os.path.join(d, 'module.json'))
        if (not gd.structured(existing) or gd.read_policy(os.path.join(d, GLOSSARY_LOCKED), existing) != policy
                or (categories is not None and existing['categories'] != document['categories'])
                or (_settings(d) and _settings(d)['punctuation_mode'] != punctuation_mode)
                or any(value and mj.get(key) != value for key, value in [('source_language',source_language),('target_language',target_language),('title',title)])):
            raise ValueError('module already exists with conflicting configuration: ' + name)
        return d
    os.makedirs(d, exist_ok=True)
    mj_path = os.path.join(d, "module.json")
    if not os.path.exists(mj_path):
        write_module_json(d, name, source_language=source_language,
                          target_language=target_language, title=title or name,
                          origin={"type": "manual"})
    for fn in (TRANSLATE_PROMPT, POLISH_PROMPT, STYLE):
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8").close()
    gl = os.path.join(d, GLOSSARY_LOCKED)
    if not os.path.exists(gl):
        gd.write_document(gl, document, policy)
    shutil.copy2(Path(__file__).parent / 'schemas/glossary.schema.json', os.path.join(d, GLOSSARY_SCHEMA))
    (Path(d) / SETTINGS).write_text(
        f'# 预设参数\n\n- 标点符号模式：{punctuation_mode}\n- 人名翻译模式：{name_mode}\n\n'
        '标点：full 为全角，half 为半角。人名：A 汉化、B 拉丁转写、C 源文、D 按姓名体系。\n'
        '输出格式及模板在每次翻译任务开始时另行选择。\n', encoding='utf8')
    mj = _read_json(mj_path)
    mj.update(glossary_format='1.0.0', glossary_policy=gd.policy_path(gl).name)
    from .artifact_io import write_json
    write_json(mj_path, mj)
    return d


def write_module_json(d: str, name: str, *, source_language="", target_language="",
                      title="", switches=None, origin=None) -> None:
    mj = {"schema_version": SCHEMA_VERSION, "name": name, "title": title or name,
          "source_language": source_language, "target_language": target_language,
          "translate_prompt": TRANSLATE_PROMPT, "polish_prompt": POLISH_PROMPT,
          "glossary_locked": GLOSSARY_LOCKED, "style": STYLE,
          "glossary_schema": GLOSSARY_SCHEMA, "settings": SETTINGS,
          "examples": EXAMPLES, "switches": switches or {},
          "origin": origin or {"type": "manual"}}
    with open(os.path.join(d, "module.json"), "w", encoding="utf-8") as f:
        json.dump(mj, f, ensure_ascii=False, indent=2)


def _copy_in(src: str, dst: str) -> bool:
    if not os.path.exists(src):
        return False
    if os.path.exists(dst):
        helpers.backup_file(dst)
    shutil.copy2(src, dst)
    return True


def load_module(name: str, work: str | None = None) -> dict:
    d = module_dir(name)
    if not os.path.isdir(d):
        raise FileNotFoundError(f"module not found: {name}")
    gl_path = os.path.join(d, GLOSSARY_LOCKED)
    gl = gd.read_document(gl_path) if os.path.exists(gl_path) else {}
    policy = gd.read_policy(gl_path, gl) if gd.structured(gl) else None
    settings = _settings(d)
    if policy is not None and settings:
        policy = {**policy, 'person_name_mode': settings['person_name_mode']}
    if os.path.isfile(os.path.join(d, GLOSSARY_SCHEMA)):
        from jsonschema import Draft202012Validator
        schema = _read_json(os.path.join(d, GLOSSARY_SCHEMA))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(gl)
    os.makedirs(home(), exist_ok=True)
    with open(os.path.join(home(), "active.json"), "w", encoding="utf-8") as f:
        json.dump({"active_module": name}, f, ensure_ascii=False, indent=2)
    copied = []
    if work:
        wdir = os.path.join(work, "work")
        os.makedirs(wdir, exist_ok=True)
        # module file -> name the existing pipeline steps consume in work/
        mapping = {GLOSSARY_LOCKED: GLOSSARY_LOCKED,
                   TRANSLATE_PROMPT: WORK_USER_PROMPT,
                   POLISH_PROMPT: 'polish_prompt.md', STYLE: 'style.md',
                   SETTINGS: SETTINGS, GLOSSARY_SCHEMA: GLOSSARY_SCHEMA}
        for src_name, dst_name in mapping.items():
            if _copy_in(_source(d, src_name), os.path.join(wdir, dst_name)):
                copied.append(dst_name)
            else:
                stale = Path(wdir) / dst_name
                if stale.is_file():
                    helpers.backup_file(str(stale))
                    stale.unlink()
        if policy is not None:
            gd.write_document(os.path.join(wdir, GLOSSARY_LOCKED), gl, policy)
            copied.append(gd.policy_path(gl_path).name)
        else:
            stale_policy = gd.policy_path(Path(wdir) / GLOSSARY_LOCKED)
            if stale_policy.is_file():
                helpers.backup_file(str(stale_policy))
                stale_policy.unlink()
        with open(os.path.join(wdir, "active_module.json"), "w", encoding="utf-8") as f:
            json.dump({"module": name, "module_dir": d,
                       "policy_sha256": gd.read_document(os.path.join(wdir, GLOSSARY_LOCKED)).get('policy_sha256') if policy else None,
                       **settings, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=2)
    return {"module": name, "module_dir": d, "work": work, "copied": copied}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Manage ainiee-translate modules")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    show = sub.add_parser("show")
    show.add_argument("name")
    create = sub.add_parser("create")
    create.add_argument("name")
    create.add_argument("--source-language", default="")
    create.add_argument("--target-language", default="")
    create.add_argument("--title", default="")
    create.add_argument('--name-mode', choices=list('ABCD'), default='D')
    create.add_argument('--punctuation-mode', choices=('full', 'half'), default='full')
    create.add_argument('--categories')
    create.add_argument('--category', dest='category_ids', action='append')
    load = sub.add_parser("load")
    load.add_argument("name")
    load.add_argument("--work", default=None)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            print(json.dumps(list_modules(), ensure_ascii=False, indent=2))
        elif a.cmd == "show":
            print(json.dumps(show_module(a.name), ensure_ascii=False, indent=2))
        elif a.cmd == "create":
            d = create_module(a.name, a.source_language, a.target_language, a.title, name_mode=a.name_mode, punctuation_mode=a.punctuation_mode, categories=a.categories, category_ids=a.category_ids)
            print(f"created module -> {d}")
        elif a.cmd == "load":
            r = load_module(a.name, a.work)
            print(json.dumps(r, ensure_ascii=False))
    except (FileNotFoundError, OSError, ValueError) as e:
        ap.error(str(e))


if __name__ == "__main__":
    main()
