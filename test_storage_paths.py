"""Regression test for storage path resolution.

- LIBRARY_DIR must follow the configured Storage Location (default_save_path)
  when it is set and writable — the Library browser must show the same folder
  captures are saved to,
- else fall back to the portable 'library' folder next to the exe/script,
- else to %LOCALAPPDATA%\\ScreenSnap\\library (never Program Files — the
  installed copy gets WinError 5 writing there),
- CONFIG_DIR must fall back to %APPDATA%\\ScreenSnap\\config the same way.

Run WITHOUT elevation: the Program Files cases rely on writes being denied.
"""
import ctypes
import os
import shutil
import sys
import tempfile
import importlib.util
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if sys.platform == 'win32':
        assert not ctypes.windll.shell32.IsUserAnAdmin(), \
            "run this test non-elevated (Program Files must be non-writable)"

    ss = _load("screensnap_paths", os.path.join(HERE, "screensnap.py"))
    LM, SM = ss.LibraryManager, ss.SettingsManager
    tmp = Path(tempfile.mkdtemp(prefix="ss-paths-test-"))
    try:
        # 1. Configured Storage Location wins (and is created if missing).
        storage = tmp / "storage"
        SM.load = classmethod(lambda cls: {'default_save_path': str(storage)})
        LM._resolved_dir = None
        assert Path(LM.LIBRARY_DIR()) == storage, "library must follow Storage Location"
        assert storage.exists(), "storage folder should be created by the probe"

        # 2. No Storage Location configured -> portable folder next to script.
        SM.load = classmethod(lambda cls: {'default_save_path': ''})
        LM._resolved_dir = None
        assert Path(LM.LIBRARY_DIR()) == Path(HERE) / "library"

        # 3. Non-writable base dir (installed copy) -> LOCALAPPDATA fallback.
        LM._resolved_dir = None
        LM._get_base_dir = staticmethod(lambda: Path(r"C:\Program Files\ScreenSnap"))
        d = str(LM.LIBRARY_DIR())
        assert "Program Files" not in d, "must never resolve into Program Files"
        assert "ScreenSnap" in d and d.lower().endswith("library")

        # 4. CONFIG_DIR: portable when writable, %APPDATA% fallback otherwise.
        SM._resolved_config_dir = None
        assert Path(SM.CONFIG_DIR()) == Path(HERE) / "config"
        SM._resolved_config_dir = None
        SM._get_base_dir = staticmethod(lambda: Path(r"C:\Program Files\ScreenSnap"))
        cd = str(SM.CONFIG_DIR())
        assert "Program Files" not in cd, "config must never resolve into Program Files"
        assert "ScreenSnap" in cd
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("ALL PASSED")


if __name__ == "__main__":
    main()
