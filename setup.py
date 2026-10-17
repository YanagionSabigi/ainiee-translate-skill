"""Include the unchanged sibling publisher in a standalone wheel."""
from pathlib import Path
import importlib.util
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py


class PublicationBuild(build_py):
    def run(self):
        # setuptools otherwise retains modules removed since an earlier build.
        generated=(Path(self.build_lib)/'ainiee_translate').resolve()
        intended=(Path(__file__).resolve().parent/'build').resolve()
        if not generated.is_relative_to(intended):
            raise ValueError('Generated package must stay inside the workspace build directory')
        if generated.exists(): shutil.rmtree(generated)
        super().run()
        # PEP 517 frontends do not have to put the project root on sys.path.
        spec=importlib.util.spec_from_file_location('_ainiee_bundle_build',Path(__file__).resolve().parent/'build.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target=Path(self.build_lib)/'ainiee_translate/publication_skill'
        for relative,source in module.publication_files(Path(__file__).parent).items():
            destination=target/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,destination)


setup(cmdclass={'build_py':PublicationBuild})
