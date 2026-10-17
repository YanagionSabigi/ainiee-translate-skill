"""Build a reproducible skill ZIP from tracked files and verify release assets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
import zipfile

import build


def digest(data):
    return hashlib.sha256(data).hexdigest()


def skill_members(repo):
    repo=Path(repo).resolve()
    skill=repo/'skills/ainiee-translate'
    tracked=subprocess.check_output(['git','ls-files','-z','--','skills/ainiee-translate'],cwd=repo)
    result={}
    for raw in tracked.split(b'\0'):
        if not raw: continue
        path=repo/raw.decode('utf8'); relative=path.relative_to(skill)
        if (path.is_symlink() or not path.resolve().is_relative_to(skill.resolve())
                or any(p.startswith('.') or p in ('__pycache__','runtime','work','output') for p in relative.parts)
                or path.suffix in ('.pyc','.log','.bak')):
            raise ValueError('Runtime, hidden or unsafe tracked skill file: '+relative.as_posix())
        result[relative.as_posix()]=path.read_bytes()
    if 'SKILL.md' not in result or 'LICENSE' not in result:
        raise ValueError('Skill distribution needs tracked SKILL.md and LICENSE')
    return result


def skill_zip(repo,output,*,check=False):
    members=skill_members(repo)
    if not check:
        Path(output).parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for relative,data in sorted(members.items()):
                info=zipfile.ZipInfo('ainiee-translate/'+relative,(2026,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o100644 << 16
                archive.writestr(info,data)
    with zipfile.ZipFile(output) as archive:
        expected={'ainiee-translate/'+k:v for k,v in members.items()}
        if set(archive.namelist())!=set(expected) or len(archive.namelist())!=len(expected):
            raise ValueError('Skill archive member mismatch')
        if any(archive.read(k)!=v for k,v in expected.items()):
            raise ValueError('Skill archive differs from tracked source')
    return members


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parent
    build.build(repo,check=True)
    metadata=json.loads((repo/'skills/ainiee-translate/release.json').read_text(encoding='utf8'))
    version=metadata['version']; package_version=version.replace('-rc.','rc')
    assert tomllib.loads((repo/'pyproject.toml').read_text(encoding='utf8'))['project']['version']==package_version
    plugin=json.loads((repo/'.claude-plugin/plugin.json').read_text(encoding='utf8'))
    market=json.loads((repo/'.claude-plugin/marketplace.json').read_text(encoding='utf8'))
    assert plugin['version']==market['version']==market['plugins'][0]['version']==version
    assert f'  version: "{version}"' in (repo/'skills/ainiee-translate/SKILL.md').read_text(encoding='utf8')
    out=repo/'dist'; archive=out/f'ainiee-translate-v{version}.zip'
    members=skill_zip(repo,archive,check=args.check)
    wheel=out/f'ainiee_translate-{package_version}-py3-none-any.whl'
    if not wheel.is_file(): raise ValueError('Build the versioned wheel before release packaging')
    assets=[archive,wheel]
    manifest=dict(metadata,skill_files={k:digest(v) for k,v in sorted(members.items())},
                  assets={p.name:digest(p.read_bytes()) for p in assets})
    manifest_path=out/'release-manifest.json'
    data=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    if not args.check: manifest_path.write_bytes(data)
    elif manifest_path.read_bytes()!=data: raise ValueError('Release manifest mismatch')
    assets.append(manifest_path)
    checksums=''.join(digest(p.read_bytes())+'  '+p.name+'\n' for p in assets).encode()
    checksum_path=out/'SHA256SUMS'
    if not args.check: checksum_path.write_bytes(checksums)
    elif checksum_path.read_bytes()!=checksums: raise ValueError('Release checksum mismatch')
    print('Verified release',metadata['tag'],'skill files:',len(members))


if __name__=='__main__': main()
