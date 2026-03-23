from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        from mypy.stubgen import generate_stubs, Options

        root = Path(self.root)
        pkg = root / "mx_remote"

        # Collect all .py source files explicitly so stubgen doesn't need to
        # resolve packages by name (which fails in an isolated build environment).
        py_files = [str(f) for f in pkg.rglob("*.py")]

        opts = Options(
            pyversion=(3, 11),
            no_import=True,
            inspect=False,
            doc_dir="",
            search_path=[str(root)],
            interpreter="",
            parse_only=True,
            ignore_errors=True,
            include_private=False,
            output_dir=str(root),
            modules=[],
            packages=[],
            files=py_files,
            verbose=False,
            quiet=True,
            export_less=False,
            include_docstrings=False,
        )
        generate_stubs(opts)

        # force_include bypasses git-based file selection (which would drop
        # .gitignored .pyi files). Keys are absolute source paths; values are
        # destination paths inside the wheel.
        pyi_files = list(root.glob("mx_remote/**/*.pyi"))
        if not pyi_files:
            raise RuntimeError(f"stubgen produced no .pyi files under {root}")
        for pyi in pyi_files:
            build_data["force_include"][str(pyi)] = str(pyi.relative_to(root))

        build_data["force_include"][str(pkg / "py.typed")] = "mx_remote/py.typed"
