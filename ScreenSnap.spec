# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['screensnap.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PIL', 'pyperclip', 'tkinter', 'pytesseract'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Scientific stack — pulled in transitively, none used by screensnap.py
        'numpy', 'scipy', 'pandas', 'matplotlib', 'sympy',
        # ML / NLP / browser-automation / media — present in user's site-packages
        'nltk', 'lark', 'torch', 'accelerate', 'transformers', 'sklearn',
        'playwright', 'selenium', 'pygame', 'yt_dlp', 'cv2',
        # Notebook / REPL stack
        'IPython', 'jupyter', 'jupyter_client', 'jupyter_core', 'ipykernel',
        'notebook', 'nbconvert', 'nbformat', 'prompt_toolkit', 'traitlets',
        # DB / web frameworks
        'sqlalchemy', 'psycopg2', 'pymysql', 'fastapi', 'flask', 'django',
        'starlette', 'uvicorn', 'httpx', 'aiohttp', 'requests',
        # XML — screensnap uses stdlib xml.etree, not lxml
        'lxml',
        # Dev tools
        'pytest', 'hypothesis', 'sphinx', 'docutils', 'cython', 'setuptools',
        'pip',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ScreenSnap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # No UPX: packed executables are a common antivirus false-positive trigger.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['screensnap.ico'],
)
