"""Create a disposable but fully functional local example project."""
import shutil
from pathlib import Path
from .model import ROOT, ReviewError
from .gitops import git, prepare


def create_demo(destination):
    destination=Path(destination).resolve()
    if destination.exists():raise ReviewError('示例目录已存在，请换一个目录名')
    destination.mkdir(parents=True)
    git(destination,'init')
    git(destination,'config','user.name','Review Workbench Demo')
    git(destination,'config','user.email','demo@localhost')
    shutil.copytree(ROOT/'examples/demo',destination/'source')
    prepare(destination,destination/'source/package.json',destination/'source/scope.json',destination/'review')
    return destination/'review'
