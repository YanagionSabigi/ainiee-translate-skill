"""Package an authoritative glossary with its schemas and human migration notes."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from jsonschema import Draft202012Validator, ValidationError, SchemaError

from . import glossary_document as gd


def _self_contained(schema):
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in ('$ref', '$dynamicRef') and isinstance(value, str) and not value.startswith('#'):
                raise ValueError('打包需要自包含 Schema：请先内联外部引用 ' + value)
            _self_contained(value)
    elif isinstance(schema, list):
        for value in schema:
            _self_contained(value)


def pack(locked, output, *, notes=None):
    locked, output = Path(locked), Path(output)
    if output.exists():
        raise FileExistsError(f'输出已存在：{output}')
    schema_dir = Path(__file__).parent / 'schemas'
    base_schema = schema_dir / 'glossary.schema.json'
    schema_path = locked.with_name(locked.stem + '.schema.json')
    if not schema_path.exists():
        schema_path = base_schema
    if os.environ.get('AINIEE_GLOSSARY_SCHEMA'):
        project_path = Path(os.environ['AINIEE_GLOSSARY_SCHEMA'])
        if (schema_path.read_bytes() != base_schema.read_bytes()
                and json.loads(schema_path.read_text(encoding='utf8')) != json.loads(project_path.read_text(encoding='utf8'))):
            raise ValueError('存在两份不同的自定义 Schema，请先合并为一份自包含 Schema 再打包')
        schema_path = project_path
    schema_raw = schema_path.read_bytes()
    schema = json.loads(schema_raw)
    _self_contained(schema)
    Draft202012Validator.check_schema(schema)
    locked_raw = locked.read_bytes()
    data = json.loads(locked_raw)
    gd.validate_document(data)
    if not gd.structured(data):
        raise ValueError('请先人工迁移旧词表为结构化 Schema，再打包')
    policy = gd.read_policy(locked, data)
    from .module import _settings
    settings = _settings(locked.parent)
    if settings and settings['person_name_mode'] != policy['person_name_mode']:
        raise ValueError('姓名预设与词表快照不同，请先加载模组，再从项目 work 目录打包')
    Draft202012Validator(schema).validate(data)
    guide = Path(__file__).parent / 'assets/docs/术语表文档.md'
    # Preserve the exact bytes of a bound policy: line endings participate in its hash.
    policy_raw = gd.policy_path(locked).read_bytes() if gd.policy_path(locked).exists() else (json.dumps(policy, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    details = ['# 本表说明', '', '本包为术语迁移包。解压到新模组并人工复核后加载；不包含原书、译文缓存或审核决定。',
               '', f"姓名模式：{policy['person_name_mode']}。分类选择：{policy.get('category_ids', '全部')}。",
               '模式属于正文渲染政策；中文译名仍记录在 chinese_translation 或 target_form。',
               '', '## 需要单独处理的内容', '']
    for group in (*gd.GROUPS, 'non_translate'):
        for row in data[group]:
            special = {key: row[key] for key in ('note', 'target_template', 'references', 'name_system') if key in row}
            if special or group == 'non_translate' or any('$' in str(row.get(k, '')) or '\\' in str(row.get(k, '')) for k in ('source_form', 'target_form')):
                label = row.get('id', row.get('marker'))
                details.append(f"- `{label}`：" + json.dumps(row, ensure_ascii=False))
    details += ['', '未列出的身份、同形词、转写和分类也须结合新项目复核。',
                'policy_sha256 绑定政策原始字节；移动时保持同目录文件完整，不从正文写法反推或覆盖目标译名。',
                '术语内中英文空格及 - / – / —— 遵循随包的标点说明。',
                '', '## 人工补充', '', Path(notes).read_text(encoding='utf8') if notes else '未提供额外说明。请在迁移前补充项目特有的译名、领域、公式及标点约定。']
    files = {'glossary.locked.json': locked_raw,
             'glossary.locked.schema.json': schema_raw,
             'glossary.base.schema.json': base_schema.read_bytes(),
             'glossary.locked.policy.json': policy_raw,
             'glossary-policy.schema.json': (schema_dir / 'glossary-policy.schema.json').read_bytes(),
             '术语表文档.md': guide.read_bytes(),
             '标点符号.md': (guide.parent / '标点符号.md').read_bytes(),
             '本表说明.md': ('\n'.join(details) + '\n').encode('utf8')}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        archive_path = Path(temporary) / 'glossary.zip'
        with ZipFile(archive_path, 'w', compression=ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
        # Exclusive creation avoids overwriting an archive created concurrently.
        with output.open('xb') as stream:
            stream.write(archive_path.read_bytes())
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--locked', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--notes', help='本表特有的人工说明 Markdown')
    args = parser.parse_args(argv)
    try:
        print(pack(args.locked, args.out, notes=args.notes))
    except (OSError, ValueError, ValidationError, SchemaError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
