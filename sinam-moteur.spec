# -*- mode: python ; coding: utf-8 -*-
# Le moteur local (serveur mlx_lm), empaqueté À PART du backend : seuls ceux qui
# choisissent le tri local le téléchargent. Voir moteur_entry.py.
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
# mlx porte ses noyaux Metal (.metallib) en données : sans collect_all, le
# binaire démarre et meurt au premier calcul sur le GPU.
for paquet in ('mlx', 'mlx_lm', 'transformers', 'tokenizers', 'safetensors'):
    d, b, h = collect_all(paquet)
    datas += d; binaries += b; hiddenimports += h

a = Analysis(
    ['moteur_entry.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Rien de tout ça ne sert à servir un modèle MLX ; transformers les tire
    # s'ils sont installés dans le venv de construction.
    excludes=['torch', 'tensorflow', 'jax', 'anthropic', 'sinam_core'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='sinam-moteur',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='sinam-moteur',
)
