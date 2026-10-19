"""Build the Windows release bundle: a no-install PyInstaller folder + zip.

What it does, in order:

1. reads the version from ``pyproject.toml``;
2. stages a clean source tree via ``git archive HEAD`` — dev-only paths are
   dropped by the ``export-ignore`` rules in ``.gitattributes`` (tests, DEVLOG,
   plans, CI config, launcher bats), and local files that were never committed
   (lab data, ``CLAUDE.md``, ``_tmp/``) cannot be in the archive at all;
3. freezes the GUI into a one-folder bundle with PyInstaller;
4. copies ``README.md`` and ``LICENSE`` next to the exe;
5. asserts the bundle carries none of the internal paths, then writes
   ``release/SDL纳米孔分析_v<version>_win64.zip``.

Usage::

    python release/build_release.py                 # build from HEAD (tree must be clean)
    python release/build_release.py --dirty         # allow a dirty tree (dev builds)
    python release/build_release.py --icon path.ico # override the app icon
    python release/build_release.py --skip-install-check  # for advanced use

Requires: PyInstaller and the runtime+GUI dependencies installed in the current
interpreter (see DEVELOPMENT.md).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "build" / "release"
STAGE = BUILD / "src"
DIST = BUILD / "dist"
WORK = BUILD / "work"
PACKAGE = BUILD / "package"
SPEC_DIR = BUILD
OUT_DIR = REPO / "release"

DEFAULT_ICON = Path(r"E:\download\1moltry_nanopore_no_person.ico")
EXE_NAME = "SDL纳米孔分析"
ENTRY_NAME = "_frozen_entry.py"

# PyInstaller cannot see these: they are imported inside functions (or by name
# through pandas' engine= string), so they must be named explicitly.
HIDDEN_IMPORTS = (
    "pyabf",
    "scipy.io",
    "openpyxl",
    "matplotlib.pyplot",
    "matplotlib.backends.backend_agg",
)

# Trim the bundle: Qt modules and dev tooling this GUI never touches.
EXCLUDES = (
    "tkinter",
    "IPython",
    "pytest",
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngineCore",
    "PyQt5.QtQuick",
    "PyQt5.QtQml",
    "PyQt5.QtDesigner",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtSql",
    "PyQt5.QtTest",
    "PyQt5.QtBluetooth",
    "PyQt5.QtNetworkAuth",
    "PyQt5.QtSensors",
    "PyQt5.QtSerialPort",
)

# Must never appear in the shipped tree (belt and braces on top of export-ignore).
FORBIDDEN = (
    "tests",
    "DEVLOG.md",
    "DEVELOPMENT.md",
    "CONTRIBUTING.md",
    ".github",
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "data",
    "release",
    "CLAUDE.md",
    "goal.md",
    "启动界面.bat",
    "启动界面-调试.bat",
    "PLAN_burst_detection.md",
    "PLAN_mods_architecture.md",
)


def read_version() -> str:
    with (REPO / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def check_requirements() -> None:
    missing = []
    for mod in ("PyInstaller", "PyQt5", "pyqtgraph", "scipy", "pandas",
                "matplotlib", "openpyxl", "pyabf"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.exit(f"缺少构建依赖：{', '.join(missing)}。先 pip install -e \".[dev]\"。")


def assert_clean_tree(allow_dirty: bool) -> None:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        return
    files = "\n".join("  " + line for line in out.splitlines()[:20])
    if allow_dirty:
        print(f"[warn] 工作区不干净，包内容取自 HEAD（未提交的改动不会进包）：\n{files}")
        return
    sys.exit(f"工作区有未提交改动，构建内容取自 HEAD 会漏掉它们：\n{files}\n"
             f"请先提交，或用 --dirty 明确接受。")


def stage_source() -> None:
    """Extract `git archive HEAD` — export-ignore rules drop the dev-only paths."""
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tar_path = Path(tmp.name)
    try:
        run(["git", "archive", "--format=tar", "-o", str(tar_path), "HEAD"], cwd=REPO)
        with tarfile.open(tar_path) as tf:
            tf.extractall(STAGE)
    finally:
        tar_path.unlink(missing_ok=True)

    leaked = [name for name in FORBIDDEN if (STAGE / name).exists()]
    if leaked:
        sys.exit(f"排除清单失效，暂存树里仍有：{leaked}；检查 .gitattributes。")
    print(f"[ok] 暂存源码树干净：{STAGE}")


def write_entry() -> None:
    (STAGE / ENTRY_NAME).write_text(
        '"""Build-time GUI entry point (not part of the repo source)."""\n'
        "from nanopore.gui.__main__ import main\n\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )


def freeze(icon: Path) -> None:
    if not icon.exists():
        sys.exit(f"图标文件不存在：{icon}（用 --icon 指定）")
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", EXE_NAME,
        "--icon", str(icon),
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(SPEC_DIR),
        "--collect-submodules", "pyabf",
    ]
    for mod in HIDDEN_IMPORTS:
        args += ["--hidden-import", mod]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    args.append(ENTRY_NAME)
    run(args, cwd=STAGE)


def assemble() -> Path:
    app_dir = DIST / EXE_NAME
    if not app_dir.exists():
        sys.exit(f"PyInstaller 未产出预期的目录：{app_dir}")
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    pkg_app = PACKAGE / EXE_NAME
    shutil.copytree(app_dir, pkg_app)

    for doc in ("README.md", "LICENSE"):
        src = STAGE / doc
        if src.exists():
            shutil.copy2(src, pkg_app / doc)
        else:
            print(f"[warn] 源树里没有 {doc}，略过")
    print(f"[ok] 发布目录：{pkg_app}")
    return pkg_app


def make_zip(pkg_app: Path, version: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT_DIR / f"{EXE_NAME}_v{version}_win64.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(pkg_app.rglob("*")):
            zf.write(path, path.relative_to(PACKAGE))
    return zip_path


def verify_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    # entries look like "SDL纳米孔分析/<...>"; only the first segment under the
    # app folder is a shipping decision — deeper names are library internals
    leaked = [n for n in names
              if len(n.split("/")) > 1 and n.split("/")[1] in FORBIDDEN]
    if leaked:
        sys.exit(f"zip 里混入内部文件：{leaked[:10]}")
    has_exe = any(n.endswith(f"{EXE_NAME}.exe") for n in names)
    has_readme = any(n.endswith("README.md") for n in names)
    print(f"[ok] zip 校验通过：{len(names)} 个条目，exe={has_exe}，README={has_readme}")


def human(nbytes: int) -> str:
    return f"{nbytes / 1024 / 1024:.0f} MB"


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 Windows 发行包（免安装 exe + zip）")
    ap.add_argument("--icon", type=Path, default=DEFAULT_ICON, help="应用图标 .ico")
    ap.add_argument("--dirty", action="store_true",
                    help="允许工作区不干净（默认要求先提交，避免包内容陈旧）")
    ap.add_argument("--skip-install-check", action="store_true",
                    help="跳过构建依赖自检")
    args = ap.parse_args()

    if not args.skip_install_check:
        check_requirements()
    version = read_version()
    print(f"构建 {EXE_NAME} v{version}")
    assert_clean_tree(args.dirty)
    stage_source()
    write_entry()
    freeze(args.icon)
    pkg_app = assemble()
    zip_path = make_zip(pkg_app, version)
    verify_zip(zip_path)

    print(f"\n完成：{zip_path}")
    print(f"  解压后体积：{human(dir_size(pkg_app))}")
    print(f"  zip 体积：  {human(zip_path.stat().st_size)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
