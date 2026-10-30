"""Launcher works both in the source checkout and in a standalone skill ZIP."""
import os
import sys
from pathlib import Path

skill_dir=Path(__file__).resolve().parents[1]
candidates=[skill_dir/'runtime',Path(__file__).resolve().parents[3]]
if os.environ.get('REVIEW_WORKBENCH_HOME'):candidates.insert(0,Path(os.environ['REVIEW_WORKBENCH_HOME']))
for root in candidates:
    if (root/'review_workbench/__main__.py').is_file():
        sys.path.insert(0,str(root))
        from review_workbench.__main__ import main
        if __name__=='__main__':main()
        break
else:
    raise SystemExit('缺少工作台运行资源。请使用完整源码目录或带 runtime/ 的独立 skill 安装包。')
