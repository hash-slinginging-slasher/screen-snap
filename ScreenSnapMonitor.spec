# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['screensnap-printscreen-monitor.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pystray', 'PIL'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'scipy', 'pandas', 'matplotlib', 'sympy',
        'nltk', 'lark', 'torch', 'accelerate', 'transformers', 'sklearn',
        'playwright', 'selenium', 'pygame', 'yt_dlp', 'cv2',
        'IPython', 'jupyter', 'jupyter_client', 'jupyter_core', 'ipykernel',
        'notebook', 'nbconvert', 'nbformat', 'prompt_toolkit', 'traitlets',
        'sqlalchemy', 'psycopg2', 'pymysql', 'fastapi', 'flask', 'django',
        'starlette', 'uvicorn', 'httpx', 'aiohttp', 'requests',
        'lxml',
        'pytest', 'hypothesis', 'sphinx', 'docutils', 'cython', 'setuptools',
        'pip', 'tkinter',
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
    name='ScreenSnapMonitor',
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
    version='monitor-version-info.txt',
)
