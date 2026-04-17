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
from pathlib import Path

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
            self.capture_count += 1
            
            # Launch ScreenSnap with region capture
            if self.screensnap_path:
                print(f"Print Screen detected - Launching ScreenSnap (capture #{self.capture_count})")
                try:
                    # Run in a new process, don't wait for it to finish
                    if self.screensnap_path.lower().endswith('.bat'):
                        cmd = ['cmd', '/c', self.screensnap_path, 'region']
                    else:
                        cmd = [self.screensnap_path, 'region']
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
                
                # Brief cooldown to prevent double-triggering
                time.sleep(0.5)
            else:
                print("ScreenSnap executable not found!")
            
            self.is_capturing = False
    
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
    
    def _on_show_status(self, icon, item):
        """Show status message."""
        print(f"ScreenSnap Print Screen Monitor is running.")
        print(f"  - Monitoring: Print Screen key")
        print(f"  - Captures this session: {self.capture_count}")
        print(f"  - ScreenSnap path: {self.screensnap_path or 'Not found'}")
    
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
        print("Right-click the tray icon to quit or show status.")
        print()
        
        # Register Print Screen key handler
        keyboard.hook_key('print screen', self.on_printscreen)
        
        # Create system tray icon
        icon = pystray.Icon(
            "screensnap_monitor",
            self._create_icon(),
            "ScreenSnap Print Screen Monitor",
            pystray.Menu(
                pystray.MenuItem("Show Status", self._on_show_status),
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
    monitor = PrintScreenMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
