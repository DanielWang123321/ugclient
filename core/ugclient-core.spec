# PyInstaller spec for the ugclient-core sidecar (--onedir). Build via scripts/build_sidecar.py.
# ufactory_genesis resolves assets relative to its package (PROJECT_ROOT = parents[2] of
# ufactory/robots/registry.py), so pyproject.toml + assets/ are placed at the bundle root (_internal/).
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
UFG = ROOT / "third_party" / "ufactory_genesis"
BUILD_EXTRA = Path(os.environ.get("UGCLIENT_BUILD_EXTRA", ROOT / "build" / "sidecar-extra"))

datas = [(str(UFG / "pyproject.toml"), "."), (str(UFG / "NOTICE"), "."), (str(UFG / "LICENSE"), ".")]
for f in (BUILD_EXTRA / "UFG_COMMIT", BUILD_EXTRA / "UFG_VERSION"):
    if f.is_file():
        datas.append((str(f), "."))
for f in (UFG / "assets" / "configs" / "runtime").rglob("*.yaml"):
    datas.append((str(f), str(f.parent.relative_to(UFG))))
for f in (UFG / "assets" / "urdf").rglob("*"):
    if f.suffix == ".urdf" or (f.suffix == ".yaml" and "default" in f.parts):
        datas.append((str(f), str(f.parent.relative_to(UFG))))

binaries = []  # PyInstaller hooks resolve pinocchio/coal shared libraries from cmeel.prefix

hiddenimports = collect_submodules("ufactory.robots") + collect_submodules("ufactory.config") + [
    "ufactory.kinematics.tcp_offset",
    "ufactory.safety.models",
    "websockets.asyncio.server",
    "ugclient_core.server",
    "coal",
    "ugclient_core.script_worker",
]
# xarm-python-sdk is imported lazily by RealBackend, so PyInstaller cannot see it; bundle it explicitly.
try:
    hiddenimports += collect_submodules("xarm")
except Exception:  # noqa: BLE001
    pass

a = Analysis(
    [str(ROOT / "core" / "sidecar_entry.py")],
    pathex=[str(ROOT / "core"), str(UFG)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "genesis", "matplotlib", "tkinter", "scipy", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ugclient-core", console=True, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ugclient-core")
