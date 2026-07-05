"""
ScreenSnap Print Screen Monitor
Background service that monitors the Print Screen key and launches ScreenSnap.
Runs silently in the system tray.
"""

import sys
import os
import threading
import subprocess
import time
import tempfile
import ctypes
import atexit
from pathlib import Path


# ── Cross-process PrtScn coordination ──────────────────────────────
# Must stay in sync with screensnap.py. When a ScreenSnap window is open it
# owns the in-app PrtScn hotkey (RegisterHotKey) and writes its PID to this
# shared marker. This monitor then stays passive so one keypress does not
# trigger both an in-app capture and a spawned one.

def _hotkey_owner_lockfile():
    return os.path.join(tempfile.gettempdir(), "screensnap-hotkey-owner.lock")


def _pid_alive(pid):
    """Robust Windows process-liveness check (os.kill(pid, 0) is unreliable)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform != 'win32':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _pid_process_name(pid):
    """Best-effort executable basename for a PID ('' if unknown)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return ''
    if pid <= 0 or sys.platform != 'win32':
        return ''
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ''
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ''
        return os.path.basename(buf.value).lower()
    finally:
        k32.CloseHandle(handle)


def _pid_is_screensnap(pid):
    """True if the PID's executable looks like ScreenSnap or a Python host.

    Guards against Windows PID reuse: a stale marker whose PID got recycled
    by an unrelated process must not make this monitor defer forever
    (PrtScn would silently go dead). Must stay in sync with screensnap.py.
    """
    if sys.platform != 'win32':
        return True
    name = _pid_process_name(pid)
    return ('screensnap' in name) or name.startswith('python')


def _hotkey_owner_pid():
    """PID of the live ScreenSnap process owning the in-app hotkey, or 0."""
    try:
        path = _hotkey_owner_lockfile()
        if not os.path.exists(path):
            return 0
        with open(path) as f:
            pid = int((f.read().strip() or "0"))
        if _pid_alive(pid) and _pid_is_screensnap(pid):
            return pid
    except Exception:
        pass
    return 0


def _hotkey_owner_active():
    """True if a live ScreenSnap window already owns the in-app PrtScn hotkey."""
    return _hotkey_owner_pid() != 0


def _bring_app_to_front():
    """Raise the running ScreenSnap app's window. True if one was found.

    The app publishes its PID via the hotkey-owner marker; find that
    process's visible top-level window (launcher or editor — only one is
    shown at a time) and bring it to the foreground.
    """
    if sys.platform != 'win32':
        return False
    owner_pid = _hotkey_owner_pid()
    if not owner_pid:
        return False

    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == owner_pid and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum_cb, 0)
    if not found:
        return False
    # Prefer a titled ScreenSnap window over helper/overlay windows
    hwnd = next((h for h, t in found if 'screensnap' in t.lower()), found[0][0])
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


# ── Monitor instance lockfile ───────────────────────────────────────
# The launcher checks this file before auto-starting a monitor, so keep it
# fresh: claim it with our own PID on startup and clear it on exit so a
# crashed/killed monitor doesn't block the next auto-start. Global (temp
# dir) so source-run and dist-run ScreenSnaps share ONE monitor — must stay
# in sync with screensnap.py's monitor_lockfile().

def _monitor_lockfile():
    return Path(tempfile.gettempdir()) / "screensnap-monitor.lock"


def _another_monitor_alive():
    """True if a different live monitor process already holds the lock."""
    try:
        path = _monitor_lockfile()
        if not path.exists():
            return False
        pid = int(path.read_text().strip() or "0")
        return pid != os.getpid() and _pid_alive(pid) and _pid_is_screensnap(pid)
    except Exception:
        return False


def _release_monitor_lock():
    try:
        path = _monitor_lockfile()
        if path.exists() and (path.read_text().strip() or "0") == str(os.getpid()):
            path.unlink()
    except Exception:
        pass


def _claim_monitor_lock():
    try:
        _monitor_lockfile().write_text(str(os.getpid()))
        atexit.register(_release_monitor_lock)
    except Exception:
        pass

def _ensure(pkg, import_name=None):
    name = import_name or pkg
    try:
        return __import__(name)
    except ImportError:
        if getattr(sys, 'frozen', False):
            raise RuntimeError(
                f"Missing bundled dependency '{pkg}'. Rebuild ScreenSnapMonitor.exe "
                f"after running: pip install {pkg}"
            )
        print(f"Installing required dependency: {pkg}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        return __import__(name)

_ensure("keyboard")
_ensure("pystray")
_ensure("Pillow", "PIL")

import keyboard
import pystray
from PIL import Image, ImageDraw


class PrintScreenMonitor:
    """Monitor Print Screen key and launch ScreenSnap."""
    
    def __init__(self):
        self.screensnap_path = self._find_screensnap()
        self.is_capturing = False  # Prevent multiple triggers
        self.icon = None
        self.capture_count = 0
        
    def _find_screensnap(self):
        """Find ScreenSnap.exe or fall back to the .bat launcher."""
        # When frozen, look next to the monitor exe first
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent

        candidates = [
            base / "ScreenSnap.exe",
            base / "dist" / "ScreenSnap.exe",
            base / "screensnap-exe.bat",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

        for parent in base.parents:
            for name in ("ScreenSnap.exe", "dist/ScreenSnap.exe", "screensnap-exe.bat"):
                p = parent / name
                if p.exists():
                    return str(p)
        return None
    
    def on_printscreen(self, e):
        """Handle Print Screen key press."""
        if e.event_type == 'down' and not self.is_capturing:
            self.is_capturing = True
            try:
                # If a ScreenSnap window is already open it owns the in-app
                # PrtScn hotkey and will handle this press itself. Stay passive
                # so one keypress doesn't spawn a second, duplicate window.
                if _hotkey_owner_active():
                    print("Print Screen detected - ScreenSnap already active, deferring to its in-app hotkey")
                    time.sleep(0.5)
                    return

                self.capture_count += 1

                # Launch ScreenSnap with region capture
                if self.screensnap_path:
                    print(f"Print Screen detected - Launching ScreenSnap (capture #{self.capture_count})")
                    self._launch_screensnap('region')
                    # Brief cooldown to prevent double-triggering
                    time.sleep(0.5)
                else:
                    print("ScreenSnap executable not found!")
            finally:
                self.is_capturing = False

    def _launch_screensnap(self, mode=None):
        """Spawn ScreenSnap detached, optionally with a capture mode."""
        if not self.screensnap_path:
            print("ScreenSnap executable not found!")
            return
        args = [mode] if mode else []
        try:
            # Run in a new process, don't wait for it to finish
            if self.screensnap_path.lower().endswith('.bat'):
                cmd = ['cmd', '/c', self.screensnap_path] + args
            else:
                cmd = [self.screensnap_path] + args
            subprocess.Popen(
                cmd,
                creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS) if sys.platform == 'win32' else 0,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as ex:
            print(f"Error launching ScreenSnap: {ex}")
    
    def _create_icon(self):
        """Create a simple system tray icon."""
        # Create a simple 64x64 icon with a camera symbol
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw a simple camera icon
        # Camera body
        draw.rounded_rectangle([10, 20, 54, 48], radius=4, fill=(70, 130, 180, 255))
        # Lens
        draw.ellipse([24, 26, 40, 42], fill=(255, 255, 255, 255))
        draw.ellipse([28, 30, 36, 38], fill=(70, 130, 180, 255))
        # Flash
        draw.rectangle([42, 16, 50, 22], fill=(200, 200, 200, 255))
        # Viewfinder bump
        draw.rounded_rectangle([20, 14, 36, 22], radius=2, fill=(70, 130, 180, 255))
        
        return image
    
    def _on_quit(self, icon, item):
        """Handle system tray quit."""
        icon.stop()
        print("ScreenSnap Print Screen Monitor stopped.")
        sys.exit(0)

    def _on_open_app(self, icon, item):
        """Raise the running ScreenSnap window, or launch the app."""
        try:
            if _bring_app_to_front():
                return
            self._launch_screensnap()
        except Exception as ex:
            print(f"Error opening ScreenSnap: {ex}")
    
    def run(self):
        """Start the Print Screen monitor."""
        if not self.screensnap_path:
            print("ERROR: ScreenSnap executable not found!")
            print("Please ensure screensnap-exe.bat or dist/ScreenSnap.exe exists.")
            input("Press Enter to exit...")
            return
        
        print("=" * 60)
        print("  ScreenSnap Print Screen Monitor")
        print("=" * 60)
        print(f"Monitoring: Print Screen (PrtScn) key")
        print(f"Launches: {self.screensnap_path}")
        print()
        print("Press Print Screen to capture a screenshot!")
        print("The system tray icon will appear in the notification area.")
        print("Right-click the tray icon to open ScreenSnap or quit.")
        print()
        
        # Register Print Screen key handler
        keyboard.hook_key('print screen', self.on_printscreen)
        
        # Create system tray icon
        icon = pystray.Icon(
            "screensnap_monitor",
            self._create_icon(),
            "ScreenSnap Print Screen Monitor",
            pystray.Menu(
                # default=True → double-clicking the tray icon opens the app
                pystray.MenuItem("Open ScreenSnap", self._on_open_app, default=True),
                pystray.MenuItem("Quit", self._on_quit)
            )
        )
        
        self.icon = icon
        icon.run()


def _kill_previous_monitors():
    """Kill any existing ScreenSnapMonitor processes (not this one)."""
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq ScreenSnapMonitor.exe', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                pid = int(parts[1])
                if pid != my_pid:
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(pid)],
                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                    )
    except Exception:
        pass


def main():
    """Main entry point."""
    _kill_previous_monitors()
    # First one wins: if a live monitor (e.g. python-run, which
    # _kill_previous_monitors can't see) already holds the lock, defer.
    if _another_monitor_alive():
        print("Another ScreenSnap monitor is already running; exiting.")
        return
    _claim_monitor_lock()
    monitor = PrintScreenMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
