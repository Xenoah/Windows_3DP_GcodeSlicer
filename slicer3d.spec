# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for 3D Slicer Pro.
Build with:  pyinstaller slicer3d.spec
"""

import sys
from pathlib import Path

block_cipher = None

# ── Hidden imports ──────────────────────────────────────────────────────────
hidden_imports = [
    # PyQt6 modules
    "PyQt6.QtOpenGLWidgets",
    "PyQt6.QtOpenGL",
    "PyQt6.sip",
    # OpenGL
    "OpenGL",
    "OpenGL.GL",
    "OpenGL.GL.shaders",
    "OpenGL.arrays",
    "OpenGL.arrays.vbo",
    "OpenGL.platform",
    "OpenGL.platform.win32",
    # trimesh + deps
    "trimesh",
    "trimesh.exchange",
    "trimesh.exchange.load",
    "trimesh.exchange.stl",
    "trimesh.exchange.obj",
    "trimesh.exchange.gltf",
    "trimesh.primitives",
    "trimesh.scene",
    "trimesh.transformations",
    # shapely
    "shapely",
    "shapely.geometry",
    "shapely.ops",
    # numpy
    "numpy",
    "numpy.core._multiarray_umath",
    # scipy (trimesh optional dep)
    "scipy",
    "scipy.sparse",
    "scipy.spatial",
    # networkx (trimesh optional dep)
    "networkx",
    # PIL
    "PIL",
    # pkg_resources
    "pkg_resources.py2_warn",
]

# ── Data files ───────────────────────────────────────────────────────────────
datas = [
    # Printer/material profiles
    ("profiles/printers.json",          "profiles"),
    ("profiles/materials.json",         "profiles"),
    ("profiles/presets",                "profiles/presets"),
    # Sample model (optional – users can load their own)
    ("sample/3DBenchy.stl",            "sample"),
]

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "test",
        "tests",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Executable ───────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # use onedir (faster startup, easier to debug)
    name="3DSlicerPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX can break OpenGL DLLs
    console=False,                  # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                      # add .ico path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="3DSlicerPro",
)
