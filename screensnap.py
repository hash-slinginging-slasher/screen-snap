#!/usr/bin/env python3
"""
ScreenSnap - Portable Screenshot & Annotation Tool
Version 1.1
"""

import sys
import os
import subprocess
import argparse
import math
from pathlib import Path

# Auto-install dependencies
def ensure_dependencies():
    """Auto-install Pillow and pyperclip if not available."""
    missing = []
    try:
        import PIL
    except ImportError:
        missing.append('Pillow')
    
    try:
        import pyperclip
    except ImportError:
        missing.append('pyperclip')
    
    if missing:
        print(f"Installing dependencies: {', '.join(missing)}...")
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing
        )
        print("Dependencies installed successfully.")

ensure_dependencies()

# Now import dependencies that were just installed
from PIL import Image, ImageGrab, ImageDraw, ImageTk
import pyperclip
import ctypes

# Enable Per-Monitor DPI awareness so that coordinate systems agree
# across ctypes.GetSystemMetrics, tkinter, and Pillow's ImageGrab.grab.
# Without this, multi-monitor setups capture the wrong screen region.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)   # System DPI Aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()     # Fallback for older Windows
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import urllib.request
import urllib.parse
import json
import base64
import io


import configparser
import datetime

# ── Midnight Architect Design System (The "Stitch" Design) ──────────
class Theme:
    """Color tokens and typography for the Midnight Architect system."""
    # Palette
    BACKGROUND = "#060e20"      # Foundation (Deep Navy)
    SURFACE = "#091328"         # Layer 1
    SURFACE_LOW = "#050b1a"     # Sunken (The Void)
    SURFACE_BRIGHT = "#1f2b49"  # High Contrast Layer
    
    PRIMARY = "#85adff"         # Key Accent
    PRIMARY_GLOW = "#a0c2ff"
    SECONDARY = "#6e9fff"       # Complementary
    TERTIARY = "#9bffce"        # Tool Highlight
    
    ON_SURFACE = "#e1e2e9"      # Main Text
    ON_SURFACE_VARIANT = "#a3aac4" # Subtitles/Labels
    OUTLINE = "#40485d"         # Borders (Low opacity)
    
    ERROR = "#ffb4ab"           # Danger
    SUCCESS = "#4CAF50"         # Save Action
    
    # Typography
    FONT_DISPLAY = ("Segoe UI Semibold", 22)
    FONT_LABEL = ("Segoe UI", 9)
    FONT_BUTTON = ("Segoe UI Semibold", 10)
    FONT_STATUS = ("Consolas", 8)

    @staticmethod
    def setup_ttk_styles():
        """Configure ttk styles to match the Midnight Architect system."""
        style = ttk.Style()
        style.theme_use('clam') # Use clam as a base for better customization
        
        # Global Backgrounds
        style.configure("TFrame", background=Theme.BACKGROUND)
        style.configure("TLabel", background=Theme.BACKGROUND, foreground=Theme.ON_SURFACE, font=Theme.FONT_LABEL)
        
        # Toolbar and Containers
        style.configure("Toolbar.TFrame", background=Theme.SURFACE)
        style.configure("Sunken.TFrame", background=Theme.SURFACE_LOW)
        
        # Modern Scrollbars (Minimalist)
        style.layout("Vertical.TScrollbar", [
            ('Vertical.Scrollbar.trough', {'children': [
                ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})
            ], 'sticky': 'ns'})
        ])
        style.configure("Vertical.TScrollbar", troughcolor=Theme.BACKGROUND, bordercolor=Theme.BACKGROUND, 
                        background=Theme.SURFACE_BRIGHT, arrowcolor=Theme.SURFACE_BRIGHT, width=8)
        
        style.layout("Horizontal.TScrollbar", [
            ('Horizontal.Scrollbar.trough', {'children': [
                ('Horizontal.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})
            ], 'sticky': 'we'})
        ])
        style.configure("Horizontal.TScrollbar", troughcolor=Theme.BACKGROUND, bordercolor=Theme.BACKGROUND, 
                        background=Theme.SURFACE_BRIGHT, arrowcolor=Theme.SURFACE_BRIGHT, width=8)

        # Tabs/Notebook
        style.configure("TNotebook", background=Theme.BACKGROUND, borderwidth=0)
        style.configure("TNotebook.Tab", background=Theme.SURFACE, foreground=Theme.ON_SURFACE_VARIANT, padding=[15, 5])
        style.map("TNotebook.Tab", background=[("selected", Theme.BACKGROUND)], foreground=[("selected", Theme.PRIMARY)])


def get_all_screens_bbox():
    """Get the bounding box for all monitors (virtual screen)."""
    try:
        # Use ctypes to get virtual screen metrics
        user32 = ctypes.windll.user32
        # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
        x = user32.GetSystemMetrics(76)
        y = user32.GetSystemMetrics(77)
        width = user32.GetSystemMetrics(78)
        height = user32.GetSystemMetrics(79)
        return (x, y, x + width, y + height)
    except Exception:
        # Fallback to single screen
        return None


# DPI_AWARENESS_CONTEXT handles (negative pseudo-handles from WinUser.h)
_DPI_CTX_PER_MONITOR_AWARE_V2 = -4
_DPI_CTX_PER_MONITOR_AWARE = -3


class _BITMAPINFOHEADER(ctypes.Structure):
    """Windows BITMAPINFOHEADER for GetDIBits()."""
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


def _bitblt_capture(left, top, width, height):
    """Capture a screen region using Windows GDI BitBlt.

    This is the same technique Windows' built-in Print Screen and Snipping
    Tool use: GetDC(NULL) → CreateCompatibleBitmap → BitBlt(SRCCOPY) →
    GetDIBits. Returns a PIL Image in RGB mode.
    """
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # ctypes signatures (required for 64-bit: HANDLE/HDC/HBITMAP are pointers)
    user32.GetDC.restype = ctypes.c_void_p
    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
    gdi32.CreateCompatibleBitmap.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    ]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.BitBlt.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    gdi32.GetDIBits.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
    ]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

    SRCCOPY = 0x00CC0020
    CAPTUREBLT = 0x40000000      # Include layered (transparent) windows
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    screen_dc = None
    mem_dc = None
    bitmap = None
    try:
        screen_dc = user32.GetDC(None)            # Desktop DC (entire virtual screen)
        if not screen_dc:
            raise RuntimeError("GetDC(NULL) failed")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            raise RuntimeError("CreateCompatibleDC failed")
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not bitmap:
            raise RuntimeError("CreateCompatibleBitmap failed")
        gdi32.SelectObject(mem_dc, bitmap)

        if not gdi32.BitBlt(
            mem_dc, 0, 0, width, height,
            screen_dc, left, top, SRCCOPY | CAPTUREBLT,
        ):
            raise RuntimeError("BitBlt failed")

        bmi = _BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.biWidth = width
        bmi.biHeight = -height      # Negative = top-down DIB (skip vertical flip)
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = BI_RGB

        buffer = (ctypes.c_ubyte * (width * height * 4))()
        if not gdi32.GetDIBits(
            mem_dc, bitmap, 0, height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS,
        ):
            raise RuntimeError("GetDIBits failed")

        # Windows DIB is BGRA; convert to RGB to match the rest of the app.
        img = Image.frombuffer(
            'RGBA', (width, height), bytes(buffer), 'raw', 'BGRA', 0, 1,
        )
        return img.convert('RGB')
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        if screen_dc:
            user32.ReleaseDC(None, screen_dc)


def capture_all_screens():
    """Capture all monitors as a single image, matching native Win+PrtScn.

    Uses Windows GDI BitBlt directly (the same path used by Windows' built-in
    Print Screen and Snipping Tool). Temporarily switches the calling thread
    to Per-Monitor V2 DPI awareness so GetSystemMetrics and BitBlt return true
    physical pixels regardless of display scaling. Falls back to Pillow's
    ImageGrab if BitBlt fails for any reason.
    """
    user32 = ctypes.windll.user32
    old_ctx = None
    set_thread_ctx = getattr(user32, 'SetThreadDpiAwarenessContext', None)
    if set_thread_ctx is not None:
        set_thread_ctx.restype = ctypes.c_void_p
        set_thread_ctx.argtypes = [ctypes.c_void_p]
        try:
            old_ctx = set_thread_ctx(ctypes.c_void_p(_DPI_CTX_PER_MONITOR_AWARE_V2))
            if not old_ctx:
                # V2 not supported on this Windows build; try V1.
                old_ctx = set_thread_ctx(ctypes.c_void_p(_DPI_CTX_PER_MONITOR_AWARE))
        except Exception:
            old_ctx = None
    try:
        # Virtual screen bounds (physical pixels thanks to DPI context above).
        left = user32.GetSystemMetrics(76)    # SM_XVIRTUALSCREEN
        top = user32.GetSystemMetrics(77)     # SM_YVIRTUALSCREEN
        width = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        try:
            return _bitblt_capture(left, top, width, height)
        except Exception:
            # Fall back to Pillow if GDI path fails.
            return ImageGrab.grab(
                bbox=(left, top, left + width, top + height),
                all_screens=True,
            )
    finally:
        if old_ctx and set_thread_ctx is not None:
            try:
                set_thread_ctx(ctypes.c_void_p(old_ctx))
            except Exception:
                pass


# ── Global hotkey (Print Screen) ───────────────────────────────────
# Registers PrintScreen as a Windows-wide hotkey so the user can
# trigger a full-screen capture without focusing the launcher.
# RegisterHotKey requires a message pump, which runs on a dedicated
# daemon thread. The hotkey callback must marshal back to the Tk
# main thread via root.after(0, ...).
_hotkey_thread = None
_hotkey_callback = None
_HOTKEY_ID = 1
_VK_SNAPSHOT = 0x2C     # Print Screen
_WM_HOTKEY = 0x0312
_MOD_NOREPEAT = 0x4000


def _hotkey_worker():
    """Background thread: register PrtScn and pump Windows messages."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, _HOTKEY_ID, _MOD_NOREPEAT, _VK_SNAPSHOT):
        # Another process owns PrtScn (OneDrive, Snipping Tool, etc.)
        print("ScreenSnap: could not register PrintScreen hotkey "
              "(another app may own it).", file=sys.stderr)
        return
    try:
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                cb = _hotkey_callback
                if cb:
                    try:
                        cb()
                    except Exception:
                        pass
    finally:
        user32.UnregisterHotKey(None, _HOTKEY_ID)


def start_global_hotkey(callback):
    """Install a PrintScreen hotkey handler (idempotent).

    `callback` is invoked from the hotkey thread; callers should marshal
    any Tk interaction back to the Tk thread via root.after(0, ...).
    """
    global _hotkey_thread, _hotkey_callback
    _hotkey_callback = callback
    if _hotkey_thread and _hotkey_thread.is_alive():
        return
    _hotkey_thread = threading.Thread(
        target=_hotkey_worker, daemon=True, name="ScreenSnap-Hotkey"
    )
    _hotkey_thread.start()


# ── Single persistent Tk root ──────────────────────────────────────
# Prevents "pyimageN doesn't exist" errors when switching between
# launcher and editor windows across multiple captures.
_app_root = None


def _get_root():
    """Get or create the single persistent Tk root."""
    global _app_root
    if _app_root is None or not _app_root.winfo_exists():
        _app_root = tk.Tk()
        _app_root.withdraw()
        Theme.setup_ttk_styles() # Apply the system design globally
    return _app_root


class ModernButton(tk.Button):
    """A pill-shaped button following the Midnight Architect design system."""
    def __init__(self, master, variant="primary", **kwargs):
        # Determine theme-based colors
        if variant == "primary":
            bg = Theme.PRIMARY
            fg = "#000000"
            abg = Theme.PRIMARY_GLOW
        elif variant == "secondary":
            bg = Theme.SURFACE_BRIGHT
            fg = Theme.ON_SURFACE
            abg = Theme.OUTLINE
        elif variant == "success":
            bg = Theme.SUCCESS
            fg = "#ffffff"
            abg = "#66BB6A"
        elif variant == "danger":
            bg = Theme.ERROR
            fg = "#ffffff"
            abg = "#FF8A80"
        elif variant == "action": # For launcher main actions
            bg = Theme.SURFACE
            fg = Theme.PRIMARY
            abg = Theme.SURFACE_BRIGHT
        else: # Default/Tool
            bg = Theme.SURFACE
            fg = Theme.ON_SURFACE_VARIANT
            abg = Theme.SURFACE_BRIGHT

        # Standard ModernButton configuration
        btn_kwargs = {
            "relief": "flat",
            "borderwidth": 0,
            "font": Theme.FONT_BUTTON,
            "cursor": "hand2",
            "bg": bg,
            "fg": fg,
            "activebackground": abg,
            "activeforeground": fg,
            "padx": 15,
            "pady": 5
        }
        btn_kwargs.update(kwargs)
        super().__init__(master, **btn_kwargs)
        
        # Rounded capsule-like look using high padding
        # In standard Tkinter, we can't easily get true rounding without images, 
        # so we focus on flat precision and color.
        self.bind("<Enter>", lambda e: self.on_enter())
        self.bind("<Leave>", lambda e: self.on_leave())
        self._bg = bg
        self._abg = abg

    def on_enter(self):
        self.config(bg=self._abg)

    def on_leave(self):
        self.config(bg=self._bg)


def _clear_root(root):
    """Remove all children from a root without destroying it."""
    for widget in root.winfo_children():
        widget.destroy()
    root.geometry('')
    root.title('')
    root.resizable(True, True)
    root.protocol('WM_DELETE_WINDOW', lambda: root.destroy())


class SettingsManager:
    """Manages application settings persistence using INI file."""

    @staticmethod
    def _get_base_dir():
        """Get the base directory (works for both .py and .exe)."""
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            return Path(sys.executable).parent
        else:
            # Running as Python script
            return Path(__file__).parent

    @classmethod
    def CONFIG_DIR(cls):
        """Get the config directory path.

        When frozen and installed under Program Files (not writable),
        fall back to %APPDATA%\\ScreenSnap\\config.
        """
        base = cls._get_base_dir()
        candidate = base / "config"
        if getattr(sys, 'frozen', False):
            base_str = str(base).lower()
            if "program files" in base_str:
                appdata = os.environ.get('APPDATA')
                if appdata:
                    return Path(appdata) / "ScreenSnap" / "config"
        return candidate

    @classmethod
    def SETTINGS_FILE(cls):
        """Get the path to settings.ini file."""
        return cls.CONFIG_DIR() / "settings.ini"

    @classmethod
    def load(cls):
        """Load settings from INI file."""
        config = configparser.ConfigParser()

        # Default settings
        defaults = {
            'default_save_path': '',
            'auto_save': 'false',
            'auto_copy_path': 'true',
            'image_format': 'png',
            'imbb_api_key': '',
            'printscreen_monitor': 'false'
        }

        # Ensure config directory exists
        config_dir = cls.CONFIG_DIR()
        config_dir.mkdir(parents=True, exist_ok=True)

        # Read existing file if it exists
        settings_file = cls.SETTINGS_FILE()
        if settings_file.exists():
            try:
                config.read(settings_file)
            except:
                pass

        # Build settings dict from file or defaults
        settings = {}
        for key, default_val in defaults.items():
            if config.has_option('Settings', key):
                settings[key] = config.get('Settings', key)
            else:
                settings[key] = default_val

        # Convert types
        settings['auto_save'] = settings['auto_save'].lower() == 'true'
        settings['auto_copy_path'] = settings['auto_copy_path'].lower() == 'true'
        settings['printscreen_monitor'] = settings['printscreen_monitor'].lower() == 'true'

        return settings

    @classmethod
    def save(cls, settings):
        """Save settings to INI file."""
        # Ensure config directory exists
        config_dir = cls.CONFIG_DIR()
        config_dir.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()
        config['Settings'] = {
            'default_save_path': settings.get('default_save_path', ''),
            'auto_save': str(settings.get('auto_save', False)).lower(),
            'auto_copy_path': str(settings.get('auto_copy_path', True)).lower(),
            'image_format': settings.get('image_format', 'png'),
            'imbb_api_key': settings.get('imbb_api_key', ''),
            'printscreen_monitor': str(settings.get('printscreen_monitor', False)).lower()
        }

        try:
            settings_file = cls.SETTINGS_FILE()
            with open(settings_file, 'w') as f:
                config.write(f)
            print(f"Settings saved to: {settings_file}")
        except Exception as e:
            print(f"Failed to save settings: {e}")


class LibraryManager:
    """Manages the screenshot library folder."""

    @staticmethod
    def _get_base_dir():
        """Get the base directory (works for both .py and .exe)."""
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        else:
            return Path(__file__).parent

    @classmethod
    def LIBRARY_DIR(cls):
        """Get the library directory path."""
        return cls._get_base_dir() / "library"

    @classmethod
    def ensure_library(cls):
        """Ensure the library directory exists."""
        lib_dir = cls.LIBRARY_DIR()
        lib_dir.mkdir(exist_ok=True)
        return lib_dir

    @classmethod
    def save_to_library(cls, image: Image.Image, format_ext='png'):
        """Save an image to the library folder with a timestamped name.
        Returns the saved file path or None on failure."""
        try:
            lib_dir = cls.ensure_library()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screensnap_{timestamp}.{format_ext}"
            file_path = lib_dir / filename
            image.save(str(file_path))
            return str(file_path)
        except Exception as e:
            print(f"Library save failed: {e}")
            return None

    @classmethod
    def list_files(cls):
        """List all image files in the library, sorted by modification time (newest first)."""
        lib_dir = cls.ensure_library()
        image_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
        files = []
        for f in lib_dir.iterdir():
            if f.is_file() and f.suffix.lower() in image_exts:
                files.append(f)
        # Sort by modification time, newest first
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return files


def upload_to_imgbb(image: Image.Image, api_key: str, auto_delete_seconds: int = 86400):
    """Upload an image to ImgBB anonymously.
    
    Args:
        image: PIL Image to upload
        api_key: ImgBB API key (from imgbb.com/api)
        auto_delete_seconds: Auto-delete after this many seconds (default: 86400 = 1 day)
    
    Returns:
        dict with 'url' (direct link), 'delete_url', or None on failure with 'error' key
    """
    if not api_key:
        return {'error': 'No ImgBB API key configured. Add your key in Settings.'}
    
    try:
        # Convert image to base64 PNG
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Build POST request
        url = f"https://api.imgbb.com/1/upload?key={api_key}"
        data = urllib.parse.urlencode({
            'image': image_b64,
            'auto-delete': str(auto_delete_seconds)
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, method='POST')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        if result.get('success'):
            return {
                'url': result['data']['url'],
                'delete_url': result['data'].get('delete_url', ''),
                'direct_url': result['data'].get('image', {}).get('url', ''),
            }
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown ImgBB error')
            return {'error': f'ImgBB upload failed: {error_msg}'}
    
    except urllib.error.URLError as e:
        return {'error': f'Network error: {e.reason}'}
    except Exception as e:
        return {'error': f'Upload failed: {e}'}


class LauncherWindow:
    """Initial launcher window with Full Screen and Region buttons."""

    def __init__(self, mode=None, save_path=None):
        self.root = _get_root()
        _clear_root(self.root)
        self.root.deiconify()
        self.root.title("ScreenSnap v1.1")
        self.root.geometry("500x560")
        self.root.resizable(False, False)
        self.root.config(bg=Theme.BACKGROUND)

        # Load settings
        self.settings = SettingsManager.load()

        # Auto-start Print Screen monitor if enabled in settings
        self._auto_start_printscreen_monitor()

        # Center window
        self.center_window()

        # Main container with padding
        main_container = tk.Frame(self.root, bg=Theme.BACKGROUND, padx=30, pady=30)
        main_container.pack(fill='both', expand=True)

        # Title
        title = tk.Label(
            main_container,
            text="ScreenSnap",
            font=("Segoe UI Semibold", 28),
            fg=Theme.PRIMARY,
            bg=Theme.BACKGROUND
        )
        title.pack(pady=(5, 0))

        subtitle = tk.Label(
            main_container,
            text="Midnight Architect Edition",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.ON_SURFACE_VARIANT,
            bg=Theme.BACKGROUND
        )
        subtitle.pack(pady=(0, 40))

        # Capture buttons
        full_btn = ModernButton(
            main_container,
            variant="success",
            text="📷  FULL SCREEN",
            command=self.capture_full,
            font=("Segoe UI Bold", 11)
        )
        full_btn.pack(fill='x', pady=8)

        region_btn = ModernButton(
            main_container,
            variant="primary",
            text="✂️  REGION SELECT",
            command=self.capture_region,
            font=("Segoe UI Bold", 11)
        )
        region_btn.pack(fill='x', pady=8)

        # Action buttons row
        row_frame = tk.Frame(main_container, bg=Theme.BACKGROUND)
        row_frame.pack(fill='x', pady=20)

        library_btn = ModernButton(
            row_frame,
            variant="action",
            text="📚 Library",
            command=self.open_library,
            width=15
        )
        library_btn.pack(side='left', expand=True, padx=(0, 5))

        open_btn = ModernButton(
            row_frame,
            variant="action",
            text="📂 Open File",
            command=self.open_file,
            width=15
        )
        open_btn.pack(side='left', expand=True, padx=(5, 0))

        # Settings and Status
        status_frame = tk.Frame(main_container, bg=Theme.SURFACE, padx=15, pady=15)
        status_frame.pack(fill='x', pady=(20, 0))
        
        # Auto-save status
        status_color = "#2E7D32" if self.settings.get('auto_save') else Theme.ON_SURFACE_VARIANT
        status_text = "✓ Auto-save active" if self.settings.get('auto_save') else "• Manual mode"
        
        tk.Label(
            status_frame,
            text=status_text,
            font=("Segoe UI Bold", 9),
            fg=status_color,
            bg=Theme.SURFACE
        ) .pack(anchor='w')
        
        if self.settings.get('default_save_path'):
            tk.Label(
                status_frame,
                text=self.settings['default_save_path'],
                font=("Segoe UI", 8),
                fg=Theme.ON_SURFACE_VARIANT,
                bg=Theme.SURFACE,
                wraplength=350,
                justify="left"
            ).pack(anchor='w', pady=(5, 0))

        # Settings button - FIXED at bottom
        settings_btn = ModernButton(
            main_container,
            variant="secondary",
            text="⚙  SYSTEM SETTINGS",
            command=self.open_settings,
            font=("Segoe UI Bold", 10)
        )
        settings_btn.pack(fill='x', side='bottom', pady=(20, 0))
        
        # Handle CLI mode if specified
        self.mode = mode
        self.save_path = save_path
        
        # Auto-execute if CLI mode specified
        if mode:
            self.root.after(100, self.auto_execute)
    
    def center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        width = 500
        height = 520
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def auto_execute(self):
        """Execute capture based on CLI mode."""
        self.root.withdraw()
        if self.mode == 'full':
            self.execute_full_capture()
        elif self.mode == 'region':
            self.execute_region_capture()

    def _auto_start_printscreen_monitor(self):
        """Auto-start the Print Screen monitor (hidden, tray-only)."""
        if not self.settings.get('printscreen_monitor', True):
            return

        import subprocess, sys, os
        from pathlib import Path

        # Locate the monitor script next to the exe (frozen) or the .py (source)
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent
        monitor_exe = base_dir / "ScreenSnapMonitor.exe"
        monitor_script = base_dir / "screensnap-printscreen-monitor.py"
        use_exe = monitor_exe.exists()
        if not use_exe and not monitor_script.exists():
            return

        # Lockfile check — avoids launching duplicates
        lock_file = base_dir / ".printscreen-monitor.lock"
        try:
            if lock_file.exists():
                pid = int(lock_file.read_text().strip() or "0")
                if pid > 0:
                    # Probe if process still alive
                    try:
                        os.kill(pid, 0)
                        return  # already running
                    except OSError:
                        pass  # stale, fall through
        except Exception:
            pass

        # Prefer pythonw.exe so no console window appears
        python_exe = sys.executable
        if getattr(sys, 'frozen', False) or os.path.basename(python_exe).lower() == 'python.exe':
            candidate = Path(python_exe).parent / 'pythonw.exe'
            if candidate.exists():
                python_exe = str(candidate)
            elif getattr(sys, 'frozen', False):
                # No bundled python — try system pythonw
                python_exe = 'pythonw'

        try:
            flags = 0
            if sys.platform == 'win32':
                flags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, 'DETACHED_PROCESS', 0)
            if use_exe:
                cmd = [str(monitor_exe)]
            else:
                cmd = [python_exe, str(monitor_script)]
            proc = subprocess.Popen(
                cmd,
                creationflags=flags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                lock_file.write_text(str(proc.pid))
            except Exception:
                pass
        except Exception as e:
            print(f"Failed to auto-start Print Screen monitor: {e}")

    def open_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self.root, self.settings)
        self.root.wait_window(dialog.dialog)
        # Reload settings after dialog closes
        self.settings = SettingsManager.load()
        # Restart launcher with updated settings
        self.root.destroy()
        new_launcher = LauncherWindow()
        new_launcher.run()

    def capture_full(self):
        """Handle full screen capture from launcher."""
        self.root.withdraw()
        self.root.after(200, self.execute_full_capture)

    def execute_full_capture(self, screenshot=None):
        """Execute full screen capture and open editor.

        If `screenshot` is provided, skip the capture step and use the
        pre-captured image (used by the PrtScn hotkey path so the launcher
        and anything else on screen are included in the shot).
        """
        try:
            if screenshot is None:
                screenshot = capture_all_screens()
            # Auto-save to library
            fmt = self.settings.get('image_format', 'png')
            lib_path = LibraryManager.save_to_library(screenshot, fmt)
            self.root.withdraw()
            AnnotationEditor(screenshot, self.settings, library_path=lib_path)
            # Editor closed — check if it was replaced by a new capture
            if getattr(_app_root, '_replacing', False):
                _app_root._replacing = False
                return  # Don't rebuild, new editor is running
            # Show launcher again
            _clear_root(self.root)
            self.root.deiconify()
            self._build_launcher_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture screen: {e}")
            self.root.deiconify()

    def _build_launcher_ui(self):
        """Build/rebuild the launcher UI on the root."""
        self.root.title("ScreenSnap v1.1")
        self.root.geometry("500x520")
        self.root.resizable(False, False)

        # Reload settings
        self.settings = SettingsManager.load()

        # Main container with padding
        main_container = ttk.Frame(self.root, padding=20)
        main_container.pack(fill='both', expand=True)

        # Title
        title = tk.Label(
            main_container,
            text="ScreenSnap",
            font=("Segoe UI", 22, "bold")
        )
        title.pack(pady=(5, 0))

        subtitle = tk.Label(
            main_container,
            text="Portable Screenshot Tool",
            font=("Segoe UI", 9),
            fg="gray"
        )
        subtitle.pack(pady=(0, 20))

        # Capture buttons
        full_btn = tk.Button(
            main_container,
            text="📷 Full Screen",
            font=("Segoe UI", 13, "bold"),
            command=self.capture_full,
            bg="#4CAF50",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=10
        )
        full_btn.pack(fill='x', pady=5)

        region_btn = tk.Button(
            main_container,
            text="✂️ Region Select",
            font=("Segoe UI", 13, "bold"),
            command=self.capture_region,
            bg="#2196F3",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=10
        )
        region_btn.pack(fill='x', pady=5)

        # Library button
        library_btn = tk.Button(
            main_container,
            text="📚 Library",
            font=("Segoe UI", 13, "bold"),
            command=self.open_library,
            bg="#607D8B",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=10
        )
        library_btn.pack(fill='x', pady=5)

        # Open File button
        open_btn = tk.Button(
            main_container,
            text="📂 Open Image File",
            font=("Segoe UI", 11),
            command=self.open_file,
            bg="#FF9800",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=8
        )
        open_btn.pack(fill='x', pady=5)

        # Spacer to push content down
        ttk.Frame(main_container).pack(expand=True)

        # Auto-save status indicator
        if self.settings.get('auto_save') and self.settings.get('default_save_path'):
            status_frame = ttk.LabelFrame(main_container, text="Auto-Save Status", padding=8)
            status_frame.pack(fill='x', pady=(0, 10))

            status_label = tk.Label(
                status_frame,
                text="✓ Enabled",
                font=("Segoe UI", 9, "bold"),
                fg="#2E7D32"
            )
            status_label.pack(side='left')

            path_label = tk.Label(
                status_frame,
                text=self.settings['default_save_path'],
                font=("Segoe UI", 8),
                fg="gray",
                wraplength=300,
                justify="left"
            )
            path_label.pack(side='left', padx=(10, 0))

        # Settings button - ALWAYS VISIBLE at bottom
        settings_btn = tk.Button(
            main_container,
            text="⚙ Settings",
            font=("Segoe UI", 12, "bold"),
            command=self.open_settings,
            bg="#9C27B0",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=10
        )
        settings_btn.pack(fill='x', side='bottom')

    def capture_region(self):
        """Handle region capture from launcher."""
        self.root.withdraw()
        self.root.after(200, self.execute_region_capture)
    
    def open_file(self):
        """Open an existing image file for editing."""
        file_path = filedialog.askopenfilename(
            title="Open Image File",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            try:
                image = Image.open(file_path)
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                # Hide launcher and open editor
                self.root.withdraw()
                AnnotationEditor(image, self.settings)
                # Check if editor was replaced
                if getattr(_app_root, '_replacing', False):
                    _app_root._replacing = False
                    return
                # Show launcher again
                _clear_root(self.root)
                self.root.deiconify()
                self._build_launcher_ui()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {e}")
                self.root.deiconify()

    def execute_region_capture(self):
        """Execute region selection and open editor."""
        try:
            # Hide launcher
            self.root.withdraw()

            # Create region selector as overlay
            selector = RegionSelector(self.root)

            if selector.result:
                # Auto-save to library
                fmt = self.settings.get('image_format', 'png')
                lib_path = LibraryManager.save_to_library(selector.result, fmt)
                editor = AnnotationEditor(selector.result, self.settings, library_path=lib_path)
                
                # Check if editor was replaced by a new capture
                if getattr(_app_root, '_replacing', False):
                    _app_root._replacing = False
                    return  # Don't rebuild, new editor is running

            # Show launcher again
            _clear_root(self.root)
            self.root.deiconify()
            self._build_launcher_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select region: {e}")
            _clear_root(self.root)
            self.root.deiconify()
            self._build_launcher_ui()

    def open_library(self):
        """Open the library browser."""
        self.root.withdraw()
        self.root.after(100, self._do_open_library)

    def _do_open_library(self):
        """Actually open the library browser."""
        try:
            LibraryBrowser(self.root, self.settings)
            # Show launcher again after browser closes
            self.root.deiconify()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open library: {e}")
            self.root.deiconify()

    def run(self):
        """Run the launcher."""
        # Install PrintScreen global hotkey (PrtScn = full screen capture)
        start_global_hotkey(self._hotkey_fire)
        self.root.mainloop()

    def _hotkey_fire(self):
        """Called from the hotkey thread. Schedules capture on the Tk thread."""
        try:
            self.root.after(0, self._on_global_hotkey)
        except Exception:
            # Root may have been destroyed between launcher rebuilds.
            pass

    def _on_global_hotkey(self):
        """Handle PrtScn. Captures exactly what's on screen right now.

        Unlike the launcher's Full Screen button (which hides the launcher
        first), this grabs the current screen state immediately so anything
        visible — including the ScreenSnap launcher itself — is captured.
        """
        try:
            if not self.root.winfo_exists():
                return
            # If the root is withdrawn, a capture or editor is already active;
            # ignore the hotkey to avoid re-entrancy.
            if self.root.state() == 'withdrawn':
                return
            # Capture BEFORE touching any windows so the shot is WYSIWYG.
            screenshot = capture_all_screens()
            self.execute_full_capture(screenshot=screenshot)
        except Exception:
            pass


class SettingsDialog:
    """Settings dialog for configuring auto-save with Midnight Architect styling."""
    
    def __init__(self, parent, settings):
        self.settings = settings.copy()
        self.result = False

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("System Settings")
        self.dialog.geometry("500x800")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.config(bg=Theme.BACKGROUND)

        # Center dialog
        self.dialog.update_idletasks()
        w, h = 500, 800
        x = (self.dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (h // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        # Scrollable main container
        self.canvas = tk.Canvas(self.dialog, bg=Theme.BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.dialog, orient='vertical', command=self.canvas.yview)
        scrollable_frame = tk.Frame(self.canvas, bg=Theme.BACKGROUND, padx=30, pady=30)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Unbind mousewheel when dialog closes
        def _on_close():
            self.canvas.unbind_all("<MouseWheel>")
            self.dialog.destroy()
        self.dialog.protocol("WM_DELETE_WINDOW", _on_close)

        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Header
        tk.Label(scrollable_frame, text="SETTINGS", font=("Segoe UI Bold", 10),
                 fg=Theme.PRIMARY, bg=Theme.BACKGROUND).pack(anchor='w', pady=(0, 25))
        
        # Sections
        def create_section(parent, title):
            f = tk.Frame(parent, bg=Theme.SURFACE, padx=20, pady=20)
            f.pack(fill='x', pady=(0, 20))
            tk.Label(f, text=title.upper(), font=("Segoe UI Bold", 8), 
                     fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(anchor='w', pady=(0, 15))
            return f

        # 1. Capture Section
        capture_f = create_section(scrollable_frame, "Capture & Save")
        
        self.auto_save_var = tk.BooleanVar(value=settings.get('auto_save', False))
        tk.Checkbutton(capture_f, text="Enable auto-save after capture", variable=self.auto_save_var,
                       font=Theme.FONT_LABEL, bg=Theme.SURFACE, fg=Theme.ON_SURFACE,
                       selectcolor=Theme.BACKGROUND, activebackground=Theme.SURFACE, 
                       activeforeground=Theme.ON_SURFACE).pack(anchor='w', pady=(0, 10))
        
        self.auto_copy_var = tk.BooleanVar(value=settings.get('auto_copy_path', True))
        tk.Checkbutton(capture_f, text="Auto-copy file path to clipboard", variable=self.auto_copy_var,
                       font=Theme.FONT_LABEL, bg=Theme.SURFACE, fg=Theme.ON_SURFACE,
                       selectcolor=Theme.BACKGROUND, activebackground=Theme.SURFACE, 
                       activeforeground=Theme.ON_SURFACE).pack(anchor='w')

        # 2. Path Section
        path_f = create_section(scrollable_frame, "Storage Location")
        self.path_var = tk.StringVar(value=settings.get('default_save_path', ''))
        path_entry_f = tk.Frame(path_f, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        path_entry_f.pack(fill='x', pady=(0, 10))
        
        tk.Entry(path_entry_f, textvariable=self.path_var, font=Theme.FONT_LABEL,
                 bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE, insertbackground=Theme.PRIMARY,
                 relief='flat', borderwidth=8).pack(side='left', fill='x', expand=True)
        
        ModernButton(path_f, text="BROWSE FOLDER", variant="secondary", 
                     command=self.browse_path, font=("Segoe UI Bold", 8)).pack(anchor='e')

        # 3. Format Section
        format_f = create_section(scrollable_frame, "Image Format")
        self.format_var = tk.StringVar(value=settings.get('image_format', 'png'))
        format_opts = tk.Frame(format_f, bg=Theme.SURFACE)
        format_opts.pack(anchor='w')
        
        for fmt in ['png', 'jpg', 'bmp']:
            tk.Radiobutton(format_opts, text=fmt.upper(), value=fmt, variable=self.format_var,
                           font=Theme.FONT_LABEL, bg=Theme.SURFACE, fg=Theme.ON_SURFACE,
                           selectcolor=Theme.BACKGROUND, activebackground=Theme.SURFACE,
                           indicatoron=True).pack(side='left', padx=(0, 20))

        # 4. ImgBB Sharing Section
        share_f = create_section(scrollable_frame, "ImgBB Sharing")
        tk.Label(share_f, text="Get a free API key at", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(anchor='w')
        link_label = tk.Label(share_f, text="imgbb.com/api", font=("Segoe UI Bold", 9),
                              fg=Theme.PRIMARY, bg=Theme.SURFACE, cursor="hand2")
        link_label.pack(anchor='w')
        link_label.bind("<Button-1>", lambda e: os.startfile("https://imgbb.com/api"))

        self.imbb_key_var = tk.StringVar(value=settings.get('imbb_api_key', ''))
        key_entry_f = tk.Frame(share_f, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        key_entry_f.pack(fill='x', pady=(10, 0))

        tk.Entry(key_entry_f, textvariable=self.imbb_key_var, font=("Consolas", 9),
                 bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE, insertbackground=Theme.PRIMARY,
                 relief='flat', borderwidth=8, show='●').pack(side='left', fill='x', expand=True)

        # 5. Print Screen Integration Section
        printscreen_f = create_section(scrollable_frame, "Print Screen Integration")
        tk.Label(printscreen_f, text="Use Print Screen (PrtScn) key to launch ScreenSnap",
                 font=Theme.FONT_LABEL, fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(anchor='w', pady=(0, 10))

        self.printscreen_var = tk.BooleanVar(value=settings.get('printscreen_monitor', False))
        tk.Checkbutton(printscreen_f, text="Enable Print Screen key monitoring",
                       variable=self.printscreen_var, font=Theme.FONT_LABEL, bg=Theme.SURFACE,
                       fg=Theme.ON_SURFACE, selectcolor=Theme.BACKGROUND, activebackground=Theme.SURFACE,
                       activeforeground=Theme.ON_SURFACE).pack(anchor='w', pady=(0, 10))

        # Status indicator
        status_frame = tk.Frame(printscreen_f, bg=Theme.SURFACE)
        status_frame.pack(anchor='w', pady=(5, 0))
        
        self.printscreen_status_label = tk.Label(status_frame, text="", font=("Segoe UI", 8),
                                                  fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE)
        self.printscreen_status_label.pack(side='left')
        
        # Check if monitor is currently running
        self._check_monitor_status()

        tk.Label(printscreen_f, text="Requires: keyboard, pystray packages (auto-installed)",
                 font=("Segoe UI", 7), fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(anchor='w', pady=(10, 0))

        # Bottom Buttons
        btn_f = tk.Frame(scrollable_frame, bg=Theme.BACKGROUND)
        btn_f.pack(side='bottom', fill='x', pady=(10, 0))
        
        ModernButton(btn_f, text="CANCEL", variant="secondary", command=_on_close, width=12).pack(side='right', padx=5)
        ModernButton(btn_f, text="✓ SAVE CHANGES", variant="primary", command=self.save_settings, width=18).pack(side='right', padx=5)
    
    def browse_path(self):
        """Browse for a folder."""
        folder = filedialog.askdirectory(title="Select Default Save Folder")
        if folder:
            self.path_var.set(folder)

    def _check_monitor_status(self):
        """Check if the Print Screen monitor is currently running."""
        try:
            import subprocess
            import re
            
            # Use wmic to find monitor processes
            result = subprocess.run(
                ['wmic', 'process', 'where', "name='python.exe' and commandline like '%screensnap-printscreen-monitor%'",
                 'get', 'ProcessId'],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Look for any PID numbers in the output
            pids = re.findall(r'\d{2,}', result.stdout)
            
            if pids:
                self.printscreen_status_label.config(text="● Monitor is running", fg="#4CAF50")
            else:
                self.printscreen_status_label.config(text="○ Monitor is not running", fg="#9E9E9E")
        except Exception as e:
            self.printscreen_status_label.config(text="○ Monitor status unknown", fg="#9E9E9E")

    def _install_monitor_dependencies(self):
        """Install required packages for Print Screen monitoring."""
        try:
            import subprocess
            import sys
            
            # Check if already installed
            try:
                import keyboard
                import pystray
                return True
            except ImportError:
                pass
            
            # Install missing dependencies
            self.printscreen_status_label.config(text="Installing dependencies...", fg="#FF9800")
            self.dialog.update()
            
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', 'keyboard', 'pystray'],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.printscreen_status_label.config(text="✓ Dependencies installed", fg="#4CAF50")
            self.dialog.update()
            return True
        except Exception as e:
            self.printscreen_status_label.config(text=f"✗ Install failed: {str(e)}", fg="#F44336")
            self.dialog.update()
            return False

    def _toggle_monitor_process(self, enable):
        """Start or stop the monitor process based on setting."""
        try:
            import subprocess
            import sys
            from pathlib import Path
            
            script_dir = Path(__file__).parent
            monitor_script = script_dir / "screensnap-printscreen-monitor.py"
            
            if not monitor_script.exists():
                self.printscreen_status_label.config(text="✗ Monitor script not found", fg="#F44336")
                return False
            
            if enable:
                # Install dependencies first
                if not self._install_monitor_dependencies():
                    return False
                
                # Start the monitor
                self.printscreen_status_label.config(text="Starting monitor...", fg="#FF9800")
                self.dialog.update()
                
                subprocess.Popen(
                    [sys.executable, str(monitor_script)],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                
                import time
                time.sleep(1)  # Give it time to start
                self._check_monitor_status()
                return True
            else:
                # Stop the monitor
                self.printscreen_status_label.config(text="Stopping monitor...", fg="#FF9800")
                self.dialog.update()
                
                # Find and kill monitor processes
                result = subprocess.run(
                    ['wmic', 'process', 'where', "name='python.exe' and commandline like '%screensnap-printscreen-monitor%'",
                     'get', 'ProcessId'],
                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                import re
                pids = re.findall(r'\d+', result.stdout)
                for pid in pids:
                    subprocess.run(
                        ['taskkill', '/F', '/PID', pid],
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                
                import time
                time.sleep(0.5)
                self._check_monitor_status()
                return True
        except Exception as e:
            self.printscreen_status_label.config(text=f"✗ Error: {str(e)}", fg="#F44336")
            self.dialog.update()
            return False

    def save_settings(self):
        """Save settings and close dialog."""
        self.settings['auto_save'] = self.auto_save_var.get()
        self.settings['default_save_path'] = self.path_var.get()
        self.settings['auto_copy_path'] = self.auto_copy_var.get()
        self.settings['image_format'] = self.format_var.get()
        self.settings['imbb_api_key'] = self.imbb_key_var.get()
        self.settings['printscreen_monitor'] = self.printscreen_var.get()

        # Validate path if auto-save is enabled
        if self.settings['auto_save'] and not self.settings['default_save_path']:
            messagebox.showwarning(
                "Warning",
                "Please select a default folder when auto-save is enabled."
            )
            return

        # Handle Print Screen monitor state change
        old_printscreen = self.settings.get('printscreen_monitor', False)
        new_printscreen = self.printscreen_var.get()
        
        if old_printscreen != new_printscreen:
            # State changed - start or stop the monitor
            if not self._toggle_monitor_process(new_printscreen):
                # If failed to toggle, don't save the change
                return

        # Save to file
        SettingsManager.save(self.settings)
        self.result = True
        self.canvas.unbind_all("<MouseWheel>")
        self.dialog.destroy()


class RegionSelector:
    """Full-screen overlay for region selection with Midnight Architect styling."""

    def __init__(self, parent):
        self.result = None
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        self.finished = False

        # Get all screens bounding box
        bbox = get_all_screens_bbox()
        if bbox:
            x, y, x2, y2 = bbox
            width = x2 - x
            height = y2 - y
        else:
            # Fallback to primary screen
            x, y = 0, 0
            width = parent.winfo_screenwidth()
            height = parent.winfo_screenheight()

        self.offset_x = x
        self.offset_y = y

        # Create full-screen transparent window
        self.root = tk.Toplevel(parent)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.4)
        self.root.configure(bg='#000000')
        self.root.config(cursor="crosshair")
        self.root.overrideredirect(True)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Canvas for overlay
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg='#000000')
        self.canvas.pack(fill='both', expand=True)

        # Dimension label (Midnight styling)
        self.dim_label = tk.Label(
            self.root,
            text="",
            font=("Segoe UI Bold", 10),
            bg=Theme.PRIMARY,
            fg="#000000",
            padx=10,
            pady=5
        )
        
        # Bind events
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.root.bind('<Escape>', self.on_escape)
        
        self.root.wait_window()
    
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.current_rect:
            self.canvas.delete(self.current_rect)
    
    def on_drag(self, event):
        if self.start_x is None: return
        if self.current_rect:
            self.canvas.delete(self.current_rect)
        
        # Draw new rectangle with Primary color
        self.current_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline=Theme.PRIMARY,
            width=2
        )
        
        width = abs(event.x - self.start_x)
        height = abs(event.y - self.start_y)
        self.dim_label.config(text=f"{width} × {height}")
        self.dim_label.place(x=event.x + 10, y=event.y + 10)
    
    def on_release(self, event):
        """Handle mouse release."""
        if self.start_x is None:
            return

        # Calculate canvas-relative region
        cx1 = min(self.start_x, event.x)
        cy1 = min(self.start_y, event.y)
        cx2 = max(self.start_x, event.x)
        cy2 = max(self.start_y, event.y)

        # Minimum size check
        if cx2 - cx1 < 10 or cy2 - cy1 < 10:
            self.root.destroy()
            return

        # Convert canvas coords to absolute screen coords
        x1 = cx1 + self.offset_x
        y1 = cy1 + self.offset_y
        x2 = cx2 + self.offset_x
        y2 = cy2 + self.offset_y

        # Hide overlay BEFORE capture so it doesn't appear in the screenshot
        self.root.withdraw()
        self.root.update_idletasks()
        import time; time.sleep(0.05)  # brief delay for screen to repaint

        # Capture the region
        try:
            screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            self.result = screenshot
        except Exception as e:
            print(f"Failed to capture region: {e}")

        self.root.destroy()
    
    def on_escape(self, event):
        """Handle ESC key."""
        self.result = None
        self.root.destroy()


class AnnotationEditor:
    """Annotation editor window."""
    
    COLORS = [
        '#F58662',  # Teardrop Coral
        '#FF0000',  # Red
        '#FF7F00',  # Orange
        '#FFFF00',  # Yellow
        '#00FF00',  # Green
        '#00FFFF',  # Cyan
        '#0000FF',  # Blue
        '#8B00FF',  # Purple
        '#FFFFFF',  # White
    ]
    
    def __init__(self, image: Image.Image, settings=None, library_path=None):
        self.image = image.copy()
        self.original_image = image.copy()
        self.history = []  # For undo
        self.redo_stack = []  # For redo
        self.current_tool = None
        self.current_color = self.COLORS[0] # #F58662
        self.stroke_width = 3
        self.drawing = False
        self.start_x = None
        self.start_y = None
        self.current_shape = None
        self.last_saved_path = None
        self.library_path = library_path
        self.settings = settings or {}

        # Zoom state — canvas is 1:1 with image at zoom=1.0. At other zoom
        # levels the image is resized for display, shape tools still work
        # (coords converted on commit), and text/step tools are view-only
        # (their canvas proxies are hidden and text is baked into a preview).
        self.zoom = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 8.0

        # Text elements list (Photoshop-like layers)
        self.text_elements = []
        self.selected_text_id = None
        self.dragging_text = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0

        # Text properties
        self.text_font_family = "arial.ttf"
        self.text_font_size = 24

        # Step tool properties
        self.step_counter = 0
        self.step_elements = []
        self.step_shape = 'teardrop'  # Default to SVG teardrop
        self.step_size = 50
        self.step_font_size = 24
        self.step_rotation = 0  # Rotation in degrees (0 = pointing right)
        self.selected_step_id = None
        self.dragging_step = False
        self.drag_step_offset_x = 0
        self.drag_step_offset_y = 0

        # Arrow tool properties
        self.arrow_style = 'filled'     # 'filled' or 'open'
        self.arrow_heads = 'single'     # 'single' or 'double'

        # Blur tool properties
        self.blur_mode = 'pixelate'    # 'pixelate' or 'gaussian'
        self.blur_intensity = 15       # block_size (pixelate) or radius (gaussian)

        # Use the shared app root as a Toplevel
        master = _get_root()
        _clear_root(master)
        self.root = tk.Toplevel(master)
        self.root.title("ScreenSnap - Annotation Editor")
        self.root.geometry("1600x850")
        self.root.config(bg=Theme.BACKGROUND)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._closed = False

        self.status_var = tk.StringVar(value="Ready")

        # Main frame
        main_frame = tk.Frame(self.root, bg=Theme.BACKGROUND)
        main_frame.pack(fill='both', expand=True)

        # Create toolbar (Tonal carving: SURFACE background)
        self.toolbar = self.create_toolbar(main_frame)
        self.toolbar.pack(side='top', fill='x', padx=0, pady=0)

        # Properties area
        self.props_container = tk.Frame(main_frame, bg=Theme.BACKGROUND)
        self.props_container.pack(side='top', fill='x', padx=20, pady=(10, 0))

        # Text properties panel (Initially hidden)
        self.text_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.text_props_frame.pack(side='top', fill='x')
        self.text_props_frame.pack_forget()

        # Text properties controls (Modern styling)
        tk.Label(self.text_props_frame, text="TEXT PROPERTIES", font=("Segoe UI Bold", 8), 
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.text_props_frame, text="Font", font=Theme.FONT_LABEL, 
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.font_family_var = tk.StringVar(value="Arial")
        font_combo = ttk.Combobox(self.text_props_frame, textvariable=self.font_family_var,
                                  values=["Arial", "Segoe UI", "Verdana", "Georgia"],
                                  state='readonly', width=15)
        font_combo.pack(side='left', padx=(0, 20))

        tk.Label(self.text_props_frame, text="Size", font=Theme.FONT_LABEL, 
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.font_size_var = tk.IntVar(value=24)
        size_spin = ttk.Spinbox(self.text_props_frame, from_=8, to=120, textvariable=self.font_size_var, width=5)
        size_spin.pack(side='left', padx=(0, 20))

        ModernButton(self.text_props_frame, text="✓ APPLY", variant="primary", 
                     command=self.update_selected_text, font=("Segoe UI Bold", 8)).pack(side='left', padx=5)
        ModernButton(self.text_props_frame, text="🗑 DELETE", variant="danger", 
                     command=self.delete_selected_text, font=("Segoe UI Bold", 8)).pack(side='left', padx=5)

        # Step properties panel
        self.step_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.step_props_frame.pack(side='top', fill='x')
        self.step_props_frame.pack_forget()

        tk.Label(self.step_props_frame, text="STEP TOOL", font=("Segoe UI Bold", 8), 
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.step_props_frame, text="Shape", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.step_shape_var = tk.StringVar(value="teardrop")
        shape_combo = ttk.Combobox(self.step_props_frame, textvariable=self.step_shape_var,
                                   values=['circle', 'square', 'rounded_rect', 'teardrop'],
                                   state='readonly', width=12)
        shape_combo.pack(side='left', padx=(0, 20))
        shape_combo.bind('<<ComboboxSelected>>', lambda e: self.update_step_shape())

        tk.Label(self.step_props_frame, text="Size", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.step_size_var = tk.IntVar(value=self.step_size)
        step_size_spin = ttk.Spinbox(self.step_props_frame, from_=16, to=120,
                                     textvariable=self.step_size_var, width=5,
                                     command=self.update_step_size)
        step_size_spin.pack(side='left', padx=(0, 20))
        step_size_spin.bind('<Return>', lambda e: self.update_step_size())
        step_size_spin.bind('<FocusOut>', lambda e: self.update_step_size())

        tk.Label(self.step_props_frame, text="Rotate", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.step_rotation_var = tk.IntVar(value=0)
        rotation_spin = ttk.Spinbox(self.step_props_frame, from_=0, to=360, increment=15,
                                    textvariable=self.step_rotation_var, width=5,
                                    command=self.update_step_rotation)
        rotation_spin.pack(side='left', padx=(0, 20))
        rotation_spin.bind('<Return>', lambda e: self.update_step_rotation())
        rotation_spin.bind('<FocusOut>', lambda e: self.update_step_rotation())

        ModernButton(self.step_props_frame, text="↺ RESET", variant="secondary",
                     command=self.reset_step_counter, font=("Segoe UI Bold", 8)).pack(side='left', padx=5)

        # Arrow properties panel
        self.arrow_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.arrow_props_frame.pack(side='top', fill='x')
        self.arrow_props_frame.pack_forget()

        tk.Label(self.arrow_props_frame, text="ARROW TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.arrow_props_frame, text="Style", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.arrow_filled_btn = ModernButton(
            self.arrow_props_frame, text="\u25b6 Filled", variant="primary",
            command=lambda: self._set_arrow_style('filled'),
            font=("Segoe UI Bold", 8))
        self.arrow_filled_btn.pack(side='left', padx=2)

        self.arrow_open_btn = ModernButton(
            self.arrow_props_frame, text="\u25b7 Open", variant="tool",
            command=lambda: self._set_arrow_style('open'),
            font=("Segoe UI Bold", 8))
        self.arrow_open_btn.pack(side='left', padx=(2, 20))

        tk.Label(self.arrow_props_frame, text="Heads", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.arrow_single_btn = ModernButton(
            self.arrow_props_frame, text="\u2192 Single", variant="primary",
            command=lambda: self._set_arrow_heads('single'),
            font=("Segoe UI Bold", 8))
        self.arrow_single_btn.pack(side='left', padx=2)

        self.arrow_double_btn = ModernButton(
            self.arrow_props_frame, text="\u2194 Double", variant="tool",
            command=lambda: self._set_arrow_heads('double'),
            font=("Segoe UI Bold", 8))
        self.arrow_double_btn.pack(side='left', padx=2)

        # Blur properties panel
        self.blur_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.blur_props_frame.pack(side='top', fill='x')
        self.blur_props_frame.pack_forget()

        tk.Label(self.blur_props_frame, text="BLUR TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.blur_props_frame, text="Mode", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.blur_pixelate_btn = ModernButton(
            self.blur_props_frame, text="\u25a6 Pixelate", variant="primary",
            command=lambda: self._set_blur_mode('pixelate'),
            font=("Segoe UI Bold", 8))
        self.blur_pixelate_btn.pack(side='left', padx=2)

        self.blur_gaussian_btn = ModernButton(
            self.blur_props_frame, text="\u25cc Blur", variant="tool",
            command=lambda: self._set_blur_mode('gaussian'),
            font=("Segoe UI Bold", 8))
        self.blur_gaussian_btn.pack(side='left', padx=(2, 20))

        tk.Label(self.blur_props_frame, text="Intensity", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.blur_intensity_var = tk.IntVar(value=15)
        blur_slider = ttk.Scale(self.blur_props_frame, from_=5, to=30,
                                variable=self.blur_intensity_var, orient='horizontal', length=120,
                                command=lambda v: setattr(self, 'blur_intensity', int(float(v))))
        blur_slider.pack(side='left', padx=(0, 5))
        self.blur_intensity_label = tk.Label(self.blur_props_frame, text="15",
                                             font=Theme.FONT_LABEL, fg=Theme.ON_SURFACE_VARIANT,
                                             bg=Theme.SURFACE, width=3)
        self.blur_intensity_label.pack(side='left')
        self.blur_intensity_var.trace_add('write', lambda *_: self.blur_intensity_label.config(
            text=str(self.blur_intensity_var.get())))

        # Canvas frame (The "Sunken" Void)
        canvas_container = tk.Frame(main_frame, bg=Theme.BACKGROUND, padx=20, pady=20)
        canvas_container.pack(side='top', fill='both', expand=True)

        self.canvas_bg = tk.Frame(canvas_container, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        self.canvas_bg.pack(fill='both', expand=True)

        # Scrollbars for zoomed navigation
        self.v_scroll = tk.Scrollbar(self.canvas_bg, orient='vertical')
        self.h_scroll = tk.Scrollbar(self.canvas_bg, orient='horizontal')
        self.canvas = tk.Canvas(
            self.canvas_bg, bg=Theme.SURFACE_LOW, highlightthickness=0,
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
        )
        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)
        self.v_scroll.pack(side='right', fill='y')
        self.h_scroll.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)

        # Grid pattern for canvas
        self.root.after(100, self.draw_canvas_grid)

        # Display image — single persistent canvas item updated via itemconfig
        self.display_image = ImageTk.PhotoImage(self.image)
        self.image_id = self.canvas.create_image(0, 0, image=self.display_image, anchor='nw')
        self.canvas.config(scrollregion=(0, 0, self.image.width, self.image.height))

        # Status Bar
        status_frame = tk.Frame(self.root, bg=Theme.SURFACE, padx=10, pady=5)
        status_frame.pack(side='bottom', fill='x')

        tk.Label(status_frame, textvariable=self.status_var, font=Theme.FONT_STATUS, 
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left')

        # Bindings
        self.canvas.bind('<Button-1>', self.on_canvas_press)
        self.canvas.bind('<B1-Motion>', self.on_canvas_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_canvas_release)
        self.canvas.bind('<Double-Button-1>', self.on_canvas_double_click)
        self.canvas.bind('<Motion>', self.on_canvas_motion)
        # Zoom is ONLY triggered by Ctrl + mouse wheel.
        # Plain wheel = vertical pan, Shift+wheel = horizontal pan.
        self.canvas.bind('<Control-MouseWheel>', self.on_mousewheel)
        self.canvas.bind('<MouseWheel>', self.on_scroll_vertical)
        self.canvas.bind('<Shift-MouseWheel>', self.on_scroll_horizontal)
        self.root.bind('<Control-z>', self.undo)
        self.root.bind('<Control-Z>', self.undo)
        self.root.bind('<Control-y>', self.redo)
        self.root.bind('<Control-Y>', self.redo)
        self.root.bind('<Control-s>', self.save)
        self.root.bind('<Escape>', self.deselect_all)
        self.root.bind('<Delete>', self.delete_selected_step)

        # Tools shortcuts
        for k, t in [('r','rectangle'), ('l','line'), ('c','circle'), ('x','crop'), ('t','text'), ('p','step')]:
            self.root.bind(f'<{k}>', lambda e, tool=t: self.set_tool(tool))
            self.root.bind(f'<{k.upper()}>', lambda e, tool=t: self.set_tool(tool))

        # Overflow tool shortcuts
        for k, t in [('a','arrow'), ('m','stamp'), ('b','bubble'), ('v','smart_move'), ('u','blur'), ('h','highlight')]:
            if t in self._implemented_overflow:
                self.root.bind(f'<{k}>', lambda e, tool=t: self.set_tool(tool))
                self.root.bind(f'<{k.upper()}>', lambda e, tool=t: self.set_tool(tool))
            else:
                self.root.bind(f'<{k}>', lambda e, tool=t: self.status_var.set(f"{tool.upper()}: Coming soon"))
                self.root.bind(f'<{k.upper()}>', lambda e, tool=t: self.status_var.set(f"{tool.upper()}: Coming soon"))

        # Initial tool and color
        self.root.after(100, lambda: self.set_tool('step'))
        self.root.after(100, lambda: self.set_color(self.COLORS[0]))

        self.root.wait_window()

    def _on_close(self):
        """Handle window close."""
        self._closed = True
        self.root.destroy()
    
    def draw_canvas_grid(self):
        """Draw a subtle dot grid on the canvas background."""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        spacing = 40
        for x in range(0, max(w, 2000), spacing):
            for y in range(0, max(h, 2000), spacing):
                self.canvas.create_oval(x, y, x+1, y+1, fill=Theme.OUTLINE, outline="", tags="grid")
        self.canvas.tag_lower("grid")

    def create_toolbar(self, parent):
        """Create the professional Midnight Architect toolbar."""
        toolbar = tk.Frame(parent, bg=Theme.SURFACE, padx=20, pady=12)

        # 1. Tools Group
        tools_frame = tk.Frame(toolbar, bg=Theme.SURFACE)
        tools_frame.pack(side='left')

        tools = [
            ('Rectangle', 'rectangle', 'R'),
            ('Line', 'line', 'L'),
            ('Circle', 'circle', 'C'),
            ('Crop', 'crop', 'X'),
            ('Text', 'text', 'T'),
            ('Step', 'step', 'P'),
        ]

        for text, tool, key in tools:
            btn = ModernButton(
                tools_frame,
                text=f"{text} ({key})",
                variant="tool",
                command=lambda t=tool: self.set_tool(t)
            )
            btn.pack(side='left', padx=2)
            setattr(self, f'{tool}_btn', btn)

        # Overflow "More" dropdown for additional tools
        self.overflow_menu_btn = tk.Menubutton(
            tools_frame,
            text="More \u25be",
            font=Theme.FONT_BUTTON,
            bg=Theme.SURFACE,
            fg=Theme.ON_SURFACE_VARIANT,
            activebackground=Theme.SURFACE_BRIGHT,
            activeforeground=Theme.ON_SURFACE,
            relief='flat',
            borderwidth=0,
            cursor='hand2',
            padx=15,
            pady=5,
        )
        self.overflow_menu_btn.pack(side='left', padx=2)

        self.overflow_menu = tk.Menu(
            self.overflow_menu_btn,
            tearoff=0,
            bg=Theme.SURFACE,
            fg=Theme.ON_SURFACE,
            activebackground=Theme.PRIMARY,
            activeforeground="#000000",
            font=Theme.FONT_BUTTON,
            borderwidth=1,
            relief='flat',
        )
        self.overflow_menu_btn['menu'] = self.overflow_menu

        self.overflow_tools = [
            ('Arrow', 'arrow', 'A'),
            ('Stamp', 'stamp', 'M'),
            ('Bubble', 'bubble', 'B'),
            ('Smart Move', 'smart_move', 'V'),
            ('Blur', 'blur', 'U'),
            ('Highlight', 'highlight', 'H'),
        ]
        self._overflow_tool_names = {t[1] for t in self.overflow_tools}
        self._implemented_overflow = {'arrow', 'highlight', 'blur'}

        for label, tool, key in self.overflow_tools:
            if tool in self._implemented_overflow:
                self.overflow_menu.add_command(
                    label=f"{label} ({key})",
                    command=lambda t=tool: self.set_tool(t),
                )
            else:
                self.overflow_menu.add_command(
                    label=f"{label} ({key}) \u2014 Coming soon",
                    state='disabled',
                )

        tk.Frame(toolbar, width=1, bg=Theme.OUTLINE).pack(side='left', fill='y', padx=20)

        # 1b. History Group (Undo / Redo — Quick Access)
        history_frame = tk.Frame(toolbar, bg=Theme.SURFACE)
        history_frame.pack(side='left')

        self.undo_btn = ModernButton(
            history_frame,
            text="↶ UNDO",
            variant="secondary",
            command=self.undo,
        )
        self.undo_btn.pack(side='left', padx=2)

        self.redo_btn = ModernButton(
            history_frame,
            text="↷ REDO",
            variant="secondary",
            command=self.redo,
        )
        self.redo_btn.pack(side='left', padx=2)

        tk.Frame(toolbar, width=1, bg=Theme.OUTLINE).pack(side='left', fill='y', padx=20)

        # 2. Colors Group
        tk.Label(toolbar, text="COLOR", font=("Segoe UI Bold", 8), fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 10))
        self.color_buttons = []
        for color in self.COLORS:
            btn = tk.Button(toolbar, bg=color, width=3, height=1, relief='flat', borderwidth=0, cursor='hand2',
                            command=lambda c=color: self.set_color(c))
            btn.pack(side='left', padx=2)
            self.color_buttons.append(btn)

        tk.Frame(toolbar, width=1, bg=Theme.OUTLINE).pack(side='left', fill='y', padx=20)

        # 3. Actions Group (Right Aligned)
        actions_frame = tk.Frame(toolbar, bg=Theme.SURFACE)
        actions_frame.pack(side='right')

        ModernButton(actions_frame, text="🏠 LAUNCHER", variant="secondary", command=self.back_to_launcher).pack(side='right', padx=5)
        ModernButton(actions_frame, text="✂️ REGION", variant="primary", command=self.capture_new_region).pack(side='right', padx=5)
        ModernButton(actions_frame, text="💾 SAVE & COPY", variant="success", command=self.save_and_copy).pack(side='right', padx=5)
        ModernButton(actions_frame, text="🔗 SHARE", variant="primary", command=self.share_to_imgbb).pack(side='right', padx=5)


        return toolbar
    def capture_new_full(self):
        """Capture full screen and open in a new editor window."""
        # Destroy current editor and signal replacement
        self._closed = True
        self.root.destroy()
        _get_root()._replacing = True

        try:
            screenshot = capture_all_screens()
            # Auto-save to library
            fmt = self.settings.get('image_format', 'png')
            lib_path = LibraryManager.save_to_library(screenshot, fmt)
            AnnotationEditor(screenshot, self.settings, library_path=lib_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture screen: {e}")

    def capture_new_region(self):
        """Capture a new region and open in a new editor window."""
        # Destroy current editor and signal replacement
        self._closed = True
        self.root.destroy()
        _get_root()._replacing = True

        # Create region selector
        try:
            selector = RegionSelector(_get_root())
            if selector.result:
                # Auto-save to library
                fmt = self.settings.get('image_format', 'png')
                lib_path = LibraryManager.save_to_library(selector.result, fmt)
                # Open new editor with new capture
                AnnotationEditor(selector.result, self.settings, library_path=lib_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture region: {e}")

    def back_to_launcher(self):
        """Close editor and return to launcher."""
        self._closed = True
        self.root.destroy()
        # No _replacing flag — launcher should rebuild
    
    def set_tool(self, tool):
        """Set the current drawing tool with Midnight Architect styling."""
        self.current_tool = tool
        self.status_var.set(f"MODE: {tool.upper()}")

        # Update primary button states (Capsule highlight)
        for t in ['rectangle', 'line', 'circle', 'crop', 'text', 'step']:
            btn = getattr(self, f'{t}_btn', None)
            if btn:
                if t == tool:
                    btn.config(bg=Theme.PRIMARY, fg="#000000")
                else:
                    btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

        # Update overflow menu button label
        if tool in self._overflow_tool_names:
            display = next(
                (lbl for lbl, t, _ in self.overflow_tools if t == tool),
                tool.title()
            )
            self.overflow_menu_btn.config(
                text=f"{display} \u25be",
                bg=Theme.PRIMARY,
                fg="#000000",
            )
        else:
            self.overflow_menu_btn.config(
                text="More \u25be",
                bg=Theme.SURFACE,
                fg=Theme.ON_SURFACE_VARIANT,
            )

        # Show/hide properties panels
        if tool == 'text':
            self.text_props_frame.pack(side='top', fill='x')
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
        elif tool == 'step':
            self.step_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
        elif tool == 'arrow':
            self.arrow_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
        elif tool == 'blur':
            self.blur_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
        else:
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.deselect_all()
    
    def _set_arrow_style(self, style):
        """Toggle arrow style between filled and open."""
        self.arrow_style = style
        if style == 'filled':
            self.arrow_filled_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_open_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
        else:
            self.arrow_open_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_filled_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

    def _set_arrow_heads(self, heads):
        """Toggle arrow heads between single and double."""
        self.arrow_heads = heads
        if heads == 'single':
            self.arrow_single_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_double_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
        else:
            self.arrow_double_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_single_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

    def _draw_arrow_on_image(self, draw, x1, y1, x2, y2, color, width, style, heads):
        """Draw an arrow with arrowhead(s) onto an ImageDraw context."""
        # Draw the shaft
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

        head_length = width * 4
        head_width = width * 3

        def _arrowhead(tip_x, tip_y, from_x, from_y):
            """Draw one arrowhead pointing at (tip_x, tip_y)."""
            angle = math.atan2(tip_y - from_y, tip_x - from_x)
            lx = tip_x - head_length * math.cos(angle) + head_width * math.sin(angle) / 2
            ly = tip_y - head_length * math.sin(angle) - head_width * math.cos(angle) / 2
            rx = tip_x - head_length * math.cos(angle) - head_width * math.sin(angle) / 2
            ry = tip_y - head_length * math.sin(angle) + head_width * math.cos(angle) / 2

            if style == 'filled':
                draw.polygon([(tip_x, tip_y), (lx, ly), (rx, ry)], fill=color)
            else:
                draw.line([(lx, ly), (tip_x, tip_y)], fill=color, width=max(1, width // 2))
                draw.line([(rx, ry), (tip_x, tip_y)], fill=color, width=max(1, width // 2))

        # Head at the end (always)
        _arrowhead(x2, y2, x1, y1)

        # Head at the start (if double)
        if heads == 'double':
            _arrowhead(x1, y1, x2, y2)

    def _set_blur_mode(self, mode):
        """Toggle blur mode between pixelate and gaussian."""
        self.blur_mode = mode
        if mode == 'pixelate':
            self.blur_pixelate_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.blur_gaussian_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
        else:
            self.blur_gaussian_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.blur_pixelate_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

    def set_color(self, color):
        """Set the current drawing color with modern highlighting."""
        self.current_color = color
        
        # Update button states
        for btn in self.color_buttons:
            if btn.cget('bg') == color.lower():
                btn.config(highlightthickness=2, highlightbackground=Theme.PRIMARY)
            else:
                btn.config(highlightthickness=0)
    
    def update_stroke(self):
        """Update stroke width from spinner."""
        try:
            self.stroke_width = int(self.stroke_var.get())
        except:
            self.stroke_width = 3
    
    def prompt_text(self, initial_text=""):
        """Show dialog to enter text."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Enter Text")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + 100
        y = self.root.winfo_rooty() + 100
        dialog.geometry(f"400x150+{x}+{y}")
        
        ttk.Label(dialog, text="Enter text:", font=("Segoe UI", 10)).pack(pady=(15, 5))
        
        text_var = tk.StringVar(value=initial_text)
        entry = ttk.Entry(dialog, textvariable=text_var, font=("Segoe UI", 11), width=40)
        entry.pack(pady=5, padx=20)
        entry.focus_set()
        entry.select_range(0, tk.END)
        
        result = [None]
        
        def on_ok():
            result[0] = text_var.get()
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side='left', padx=5)
        
        # Bind Enter key
        entry.bind('<Return>', lambda e: on_ok())
        
        dialog.wait_window()
        return result[0]
    
    def add_text_element(self, x, y, text=None):
        """Add a new text element to the canvas."""
        # Prompt for text if not provided
        if text is None:
            text = self.prompt_text()
            if not text:
                return

        # Snapshot the pre-mutation state so undo can remove this text.
        self.save_state()

        # Create text element
        text_element = {
            'id': len(self.text_elements),
            'text': text,
            'x': x,
            'y': y,
            'color': self.current_color,
            'font_family': self.font_family_var.get(),
            'font_size': self.font_size_var.get(),
            'canvas_id': None
        }
        
        # Get font
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(f"{text_element['font_family'].lower().replace(' ', '')}.ttf", text_element['font_size'])
        except:
            try:
                font = ImageFont.truetype("arial.ttf", text_element['font_size'])
            except:
                font = ImageFont.load_default()
        
        # Draw text on temporary image to get dimensions
        temp_img = Image.new('RGB', (1, 1))
        draw = ImageDraw.Draw(temp_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Add to canvas at canvas-space coordinates with a zoom-scaled font.
        z = self.zoom if self.zoom else 1.0
        canvas_id = self.canvas.create_text(
            x * z, y * z,
            text=text,
            fill=text_element['color'],
            font=(text_element['font_family'],
                  max(1, int(round(text_element['font_size'] * z)))),
            anchor='nw'
        )
        text_element['canvas_id'] = canvas_id
        text_element['width'] = text_width
        text_element['height'] = text_height

        self.text_elements.append(text_element)
        self.select_text_element(text_element['id'])
        self.status_var.set(f"Text added: '{text}'")
    
    def select_text_element(self, text_id):
        """Select a text element and show blinking cursor."""
        self.deselect_all()
        self.selected_text_id = text_id
        
        # Find the text element
        text_elem = None
        for elem in self.text_elements:
            if elem['id'] == text_id:
                text_elem = elem
                break
        
        if not text_elem:
            return
        
        # Update properties panel
        self.font_family_var.set(text_elem['font_family'])
        self.font_size_var.set(text_elem['font_size'])
        
        # Draw blinking cursor at the START of text (canvas-space coords)
        z = self.zoom if self.zoom else 1.0
        cursor_x = text_elem['x'] * z
        cursor_y1 = text_elem['y'] * z
        cursor_y2 = (text_elem['y'] + text_elem['height']) * z

        text_elem['cursor_id'] = self.canvas.create_line(
            cursor_x, cursor_y1, cursor_x, cursor_y2,
            fill='#2196F3',
            width=2,
            tags='selection'
        )
        
        # Start blinking
        self._blink_cursor(visible=True)
        
        self.status_var.set(f"Selected: '{text_elem['text']}' (drag to move, double-click to edit)")
    
    def _blink_cursor(self, visible):
        """Blink the text selection cursor."""
        if self.selected_text_id is None:
            return
        
        # Find selected text element
        for elem in self.text_elements:
            if elem['id'] == self.selected_text_id and 'cursor_id' in elem:
                if visible:
                    self.canvas.itemconfig(elem['cursor_id'], state='normal')
                else:
                    self.canvas.itemconfig(elem['cursor_id'], state='hidden')
                
                # Schedule next blink
                self.root.after(500, lambda: self._blink_cursor(not visible))
                break
    
    def deselect_all(self, event=None):
        """Deselect all text and step elements."""
        self.selected_text_id = None
        self.selected_step_id = None
        # Remove all selection visuals (text cursors + step borders)
        self.canvas.delete('selection')
        for elem in self.text_elements:
            if 'cursor_id' in elem:
                del elem['cursor_id']
        for elem in self.step_elements:
            if 'selection_id' in elem:
                del elem['selection_id']
    
    def delete_selected_text(self, event=None):
        """Delete the selected text element."""
        if self.selected_text_id is None:
            return

        # Find and remove from canvas
        for i, elem in enumerate(self.text_elements):
            if elem['id'] == self.selected_text_id:
                # Snapshot before mutation so undo can bring the text back.
                self.save_state()
                if elem['canvas_id']:
                    self.canvas.delete(elem['canvas_id'])
                self.text_elements.pop(i)
                self.selected_text_id = None
                self.status_var.set("Text deleted")
                break
    
    def update_selected_text(self):
        """Update the selected text element with new properties."""
        if self.selected_text_id is None:
            return

        # Find the text element
        for elem in self.text_elements:
            if elem['id'] == self.selected_text_id:
                # Snapshot before mutation so undo can revert the edit.
                self.save_state()
                # Update properties
                elem['font_family'] = self.font_family_var.get()
                elem['font_size'] = self.font_size_var.get()
                elem['color'] = self.current_color
                
                # Delete old canvas item
                if elem['canvas_id']:
                    self.canvas.delete(elem['canvas_id'])
                
                # Get font
                try:
                    from PIL import ImageFont
                    font = ImageFont.truetype(f"{elem['font_family'].lower().replace(' ', '')}.ttf", elem['font_size'])
                except:
                    try:
                        font = ImageFont.truetype("arial.ttf", elem['font_size'])
                    except:
                        font = ImageFont.load_default()
                
                # Recreate on canvas at canvas-space coords with zoomed font
                z = self.zoom if self.zoom else 1.0
                elem['canvas_id'] = self.canvas.create_text(
                    elem['x'] * z, elem['y'] * z,
                    text=elem['text'],
                    fill=elem['color'],
                    font=(elem['font_family'],
                          max(1, int(round(elem['font_size'] * z)))),
                    anchor='nw'
                )

                # Update dimensions (stored in image space)
                temp_img = Image.new('RGB', (1, 1))
                draw = ImageDraw.Draw(temp_img)
                bbox = draw.textbbox((0, 0), elem['text'], font=font)
                elem['width'] = bbox[2] - bbox[0]
                elem['height'] = bbox[3] - bbox[1]

                # Update cursor position (canvas-space)
                self.canvas.delete('selection')
                cursor_x = elem['x'] * z
                cursor_y1 = elem['y'] * z
                cursor_y2 = (elem['y'] + elem['height']) * z

                elem['cursor_id'] = self.canvas.create_line(
                    cursor_x, cursor_y1, cursor_x, cursor_y2,
                    fill='#2196F3',
                    width=2,
                    tags='selection'
                )
                break
    
    def find_text_at_position(self, x, y):
        """Find text element at given position."""
        # Search in reverse order (top-most first)
        for elem in reversed(self.text_elements):
            x1 = elem['x']
            y1 = elem['y']
            x2 = x1 + elem['width']
            y2 = y1 + elem['height']

            if x1 <= x <= x2 and y1 <= y <= y2:
                return elem

        return None

    def find_step_at_position(self, x, y):
        """Find step element at given position."""
        # Search in reverse order (top-most first)
        for elem in reversed(self.step_elements):
            x1 = elem['x']
            y1 = elem['y']
            x2 = x1 + elem['width']
            y2 = y1 + elem['height']

            if x1 <= x <= x2 and y1 <= y <= y2:
                return elem

        return None

    def _render_step_image(self, elem, zoom=1.0):
        """Render a step element to a PhotoImage, optionally scaled by `zoom`.

        At ``zoom`` = 1.0 the returned tile matches the element's
        image-space size. Larger/smaller zooms produce a correspondingly
        larger/smaller tile so the step lines up with the zoomed canvas
        background. The 4× supersampling is still performed in image
        space, then the final downsample targets the zoomed size, which
        keeps edges crisp at arbitrary zoom levels.
        Returns (PhotoImage, width, height) for canvas display.
        """
        from PIL import ImageFilter

        step_size = elem['size']
        shape = elem['shape']
        fill_color = elem['color']
        text_color = elem.get('text_color', 'white')
        step_num = elem['number']
        font_size = max(8, int(round(step_size * 0.47 * zoom)))

        # Dimensions
        if shape == 'rounded_rect':
            rect_w = step_size * 1.5
            rect_h = step_size * 1.2
        elif shape == 'teardrop':
            rect_w = step_size * 1.4
            rect_h = step_size
        else:
            rect_w = step_size
            rect_h = step_size

        # Parse fill color
        if isinstance(fill_color, str) and fill_color.startswith('#'):
            r = int(fill_color[1:3], 16)
            g = int(fill_color[3:5], 16)
            b = int(fill_color[5:7], 16)
            fill_color = (r, g, b, 255)

        # Supersampling
        SS = 4
        pad = 10
        sw = int(rect_w) + pad * 2
        sh = int(rect_h) + pad * 2
        ss_w, ss_h = sw * SS, sh * SS

        shadow_offset_x = 2 * SS
        shadow_offset_y = 4 * SS
        shadow_blur_radius = 8 * SS
        shadow_alpha = 140

        # Teardrop polygon helper
        def get_poly_pts(origin_x, origin_y, scale, off_x=0, off_y=0):
            pts = []
            p0, p1, p2, p3 = (50, 10), (100, 10), (135, 50), (135, 50)
            for i in range(21):
                t = i / 20.0
                px = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                py = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            p0, p1, p2, p3 = (135, 50), (135, 50), (100, 90), (50, 90)
            for i in range(1, 21):
                t = i / 20.0
                px = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                py = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            for i in range(1, 41):
                angle = math.pi/2 + (i / 40.0) * math.pi
                px = 50 + 40 * math.cos(angle)
                py = 50 + 40 * math.sin(angle)
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            return pts

        # Center the shape in the supersampled tile
        mx = pad * SS
        my = pad * SS
        ss_scale = (step_size * SS) / 100.0

        shadow_layer = Image.new('RGBA', (ss_w, ss_h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shape_layer = Image.new('RGBA', (ss_w, ss_h), (0, 0, 0, 0))
        shape_draw = ImageDraw.Draw(shape_layer)
        shadow_rgba = (0, 0, 0, shadow_alpha)

        if shape == 'circle':
            shadow_draw.ellipse([mx + shadow_offset_x, my + shadow_offset_y,
                                 mx + step_size * SS + shadow_offset_x, my + step_size * SS + shadow_offset_y],
                                fill=shadow_rgba)
            shape_draw.ellipse([mx, my, mx + step_size * SS, my + step_size * SS], fill=fill_color)
        elif shape == 'square':
            shadow_draw.rounded_rectangle([mx + shadow_offset_x, my + shadow_offset_y,
                                           mx + step_size * SS + shadow_offset_x, my + step_size * SS + shadow_offset_y],
                                          radius=6 * SS, fill=shadow_rgba)
            shape_draw.rounded_rectangle([mx, my, mx + step_size * SS, my + step_size * SS],
                                         radius=6 * SS, fill=fill_color)
        elif shape == 'rounded_rect':
            radius_ss = (int(rect_h) // 2) * SS
            shadow_draw.rounded_rectangle([mx + shadow_offset_x, my + shadow_offset_y,
                                           mx + int(rect_w) * SS + shadow_offset_x, my + int(rect_h) * SS + shadow_offset_y],
                                          radius=radius_ss, fill=shadow_rgba)
            shape_draw.rounded_rectangle([mx, my, mx + int(rect_w) * SS, my + int(rect_h) * SS],
                                         radius=radius_ss, fill=fill_color)
        elif shape == 'teardrop':
            shadow_draw.polygon(get_poly_pts(mx, my, ss_scale, shadow_offset_x, shadow_offset_y), fill=shadow_rgba)
            shape_draw.polygon(get_poly_pts(mx, my, ss_scale), fill=fill_color)

        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur_radius))
        
        # Apply rotation to shape only (not the number) - only for teardrop
        rotation = elem.get('rotation', 0)
        if rotation and rotation % 360 != 0 and shape == 'teardrop':
            # Rotate only the shape layer
            shape_layer = shape_layer.rotate(-rotation, resample=Image.BICUBIC, expand=True, center=(ss_w/2, ss_h/2))
            # Adjust shadow to match expanded shape
            new_ss_w = shape_layer.width
            new_ss_h = shape_layer.height
            shadow_layer_expanded = Image.new('RGBA', (new_ss_w, new_ss_h), (0, 0, 0, 0))
            offset_x = (new_ss_w - ss_w) // 2
            offset_y = (new_ss_h - ss_h) // 2
            shadow_layer_expanded.paste(shadow_layer, (offset_x, offset_y))
            tile = Image.alpha_composite(shadow_layer_expanded, shape_layer)
        else:
            tile = Image.alpha_composite(shadow_layer, shape_layer)

        target_w = max(1, int(round(sw * zoom)))
        target_h = max(1, int(round(sh * zoom)))
        tile = tile.resize((target_w, target_h), Image.LANCZOS)

        # Draw number on top (never rotated)
        try:
            from PIL import ImageFont
            font = None
            for f in ["segoeuib.ttf", "arialbd.ttf", "Verdana_Bold.ttf"]:
                try:
                    font = ImageFont.truetype(f, font_size)
                    break
                except: continue
            if not font:
                font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        draw = ImageDraw.Draw(tile)
        tcx = tile.width / 2
        tcy = tile.height / 2
        draw.text((tcx, tcy), str(step_num), fill=text_color, font=font, anchor="mm")

        # Convert to PhotoImage
        photo = ImageTk.PhotoImage(tile)
        return photo, tile.width, tile.height

    def add_step_element(self, x, y):
        """Add a numbered step marker at the given position (canvas-only until save)."""
        # Snapshot the pre-mutation state so undo can remove this step and
        # restore the previous step_counter value.
        self.save_state()

        self.step_counter += 1
        step_num = self.step_counter

        half_size = self.step_size // 2
        x_pos = x - half_size
        y_pos = y - half_size

        # Marker dimensions
        if self.step_shape == 'rounded_rect':
            rect_width = self.step_size * 1.5
            rect_height = self.step_size * 1.2
        elif self.step_shape == 'teardrop':
            rect_width = self.step_size * 1.4
            rect_height = self.step_size
        else:
            rect_width = self.step_size
            rect_height = self.step_size

        # Fill colour
        fill_color = self.current_color
        if isinstance(fill_color, str) and fill_color.startswith('#'):
            r = int(fill_color[1:3], 16)
            g = int(fill_color[3:5], 16)
            b = int(fill_color[5:7], 16)
            fill_color = (r, g, b, 255)

        fill_luma = 0.299 * fill_color[0] + 0.587 * fill_color[1] + 0.114 * fill_color[2]
        text_color = 'black' if fill_luma > 150 else 'white'

        # Build element data
        elem = {
            'id': step_num,
            'number': step_num,
            'x': x_pos,
            'y': y_pos,
            'size': self.step_size,
            'width': rect_width,
            'height': rect_height,
            'shape': self.step_shape,
            'color': self.current_color,
            'text_color': text_color,
            'rotation': self.step_rotation,
        }

        # Render at the current zoom so the overlay lines up with the
        # zoomed canvas background.
        z = self.zoom if self.zoom else 1.0
        photo, img_w, img_h = self._render_step_image(elem, zoom=z)

        # Store photo reference to prevent GC
        elem['photo'] = photo

        # Display on canvas as image at canvas-space coordinates.
        img_id = self.canvas.create_image(
            x_pos * z, y_pos * z, image=photo, anchor='nw'
        )
        elem['img_id'] = img_id

        self.step_elements.append(elem)
        self.status_var.set(f"Step {step_num} added")

    def update_step_shape(self):
        """Update step shape from dropdown. Also updates selected step if any."""
        self.step_shape = self.step_shape_var.get()
        if self.selected_step_id is not None:
            for elem in self.step_elements:
                if elem['id'] == self.selected_step_id:
                    # Snapshot before mutation so undo can revert the change.
                    self.save_state()
                    elem['shape'] = self.step_shape
                    if elem['shape'] == 'rounded_rect':
                        elem['width'] = elem['size'] * 1.5
                        elem['height'] = elem['size'] * 1.2
                    elif elem['shape'] == 'teardrop':
                        elem['width'] = elem['size'] * 1.4
                        elem['height'] = elem['size']
                    else:
                        elem['width'] = elem['size']
                        elem['height'] = elem['size']
                    self._rebuild_step_canvas(elem)
                    break
        self.status_var.set(f"Step shape: {self.step_shape}")

    def update_step_size(self):
        """Update step size from spinner. Also updates selected step if any."""
        try:
            new_size = int(self.step_size_var.get())
        except (tk.TclError, ValueError):
            new_size = 30
        new_size = max(16, min(120, new_size))
        self.step_size = new_size
        self.step_font_size = max(8, int(round(new_size * 0.47)))
        if self.step_size_var.get() != new_size:
            self.step_size_var.set(new_size)
        if self.selected_step_id is not None:
            for elem in self.step_elements:
                if elem['id'] == self.selected_step_id:
                    # Snapshot before mutation so undo can revert the change.
                    self.save_state()
                    elem['size'] = new_size
                    if elem['shape'] == 'rounded_rect':
                        elem['width'] = new_size * 1.5
                        elem['height'] = new_size * 1.2
                    elif elem['shape'] == 'teardrop':
                        elem['width'] = new_size * 1.4
                        elem['height'] = new_size
                    else:
                        elem['width'] = new_size
                        elem['height'] = new_size
                    self._rebuild_step_canvas(elem)
                    break
        self.status_var.set(f"Step size: {new_size}")

    def update_step_rotation(self):
        """Update step rotation from spinner. Also updates selected step if any."""
        try:
            new_rot = int(self.step_rotation_var.get())
        except (tk.TclError, ValueError):
            new_rot = 0
        new_rot = new_rot % 360
        self.step_rotation = new_rot
        if self.step_rotation_var.get() != new_rot:
            self.step_rotation_var.set(new_rot)
        if self.selected_step_id is not None:
            for elem in self.step_elements:
                if elem['id'] == self.selected_step_id:
                    # Snapshot before mutation so undo can revert the change.
                    self.save_state()
                    elem['rotation'] = new_rot
                    self._rebuild_step_canvas(elem)
                    break
        self.status_var.set(f"Step rotation: {new_rot}°")

    def _rebuild_step_canvas(self, elem):
        """Rebuild canvas image for a step after shape/size change."""
        if 'img_id' in elem:
            self.canvas.delete(elem['img_id'])
        if 'selection_id' in elem:
            self.canvas.delete(elem['selection_id'])

        z = self.zoom if self.zoom else 1.0
        photo, img_w, img_h = self._render_step_image(elem, zoom=z)
        elem['photo'] = photo
        elem['img_id'] = self.canvas.create_image(
            elem['x'] * z, elem['y'] * z, image=photo, anchor='nw'
        )

        # Redraw selection border at canvas-space coordinates
        pad = 4
        elem['selection_id'] = self.canvas.create_rectangle(
            (elem['x'] - pad) * z, (elem['y'] - pad) * z,
            (elem['x'] + elem['width'] + pad) * z,
            (elem['y'] + elem['height'] + pad) * z,
            outline=Theme.PRIMARY, width=2, dash=(4, 4), tags='selection')

    def reset_step_counter(self):
        """Reset the step counter to 0."""
        self.step_counter = 0
        self.status_var.set("Step counter reset to 0")

    def delete_last_step(self):
        """Delete the last step element (canvas-only)."""
        if not self.step_elements:
            self.status_var.set("No steps to delete")
            return

        # Snapshot the pre-mutation state so undo can bring the step back.
        self.save_state()

        last_step = self.step_elements.pop()
        if 'img_id' in last_step:
            self.canvas.delete(last_step['img_id'])
        if 'selection_id' in last_step:
            self.canvas.delete(last_step['selection_id'])

        self.step_counter -= 1
        self.status_var.set(f"Deleted step {last_step['number']}")

    def refresh_all_steps(self):
        """Refresh all step elements on canvas (used after undo/redo)."""
        pass

    def select_step_element(self, step_id):
        """Select a step element and show selection border."""
        self.deselect_all()
        self.selected_step_id = step_id

        z = self.zoom if self.zoom else 1.0
        for elem in self.step_elements:
            if elem['id'] == step_id:
                pad = 4
                x1 = (elem['x'] - pad) * z
                y1 = (elem['y'] - pad) * z
                x2 = (elem['x'] + elem['width'] + pad) * z
                y2 = (elem['y'] + elem['height'] + pad) * z

                elem['selection_id'] = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline=Theme.PRIMARY,
                    width=2,
                    dash=(4, 4),
                    tags='selection'
                )
                self.step_shape_var.set(elem['shape'])
                self.step_size_var.set(elem['size'])
                self.step_rotation_var.set(elem.get('rotation', 0))
                self.step_props_frame.pack(side='top', fill='x')
                self.text_props_frame.pack_forget()
                self.status_var.set(f"Step {elem['number']} selected — drag to move, Delete to remove")
                break

    def deselect_step_element(self):
        """Remove step selection border."""
        for elem in self.step_elements:
            if 'selection_id' in elem:
                self.canvas.delete(elem['selection_id'])
                del elem['selection_id']
        self.selected_step_id = None

    def delete_selected_step(self, event=None):
        """Delete the selected step element."""
        if self.selected_step_id is None:
            return
        for i, elem in enumerate(self.step_elements):
            if elem['id'] == self.selected_step_id:
                # Snapshot before mutation so undo can restore the step.
                self.save_state()
                if 'img_id' in elem:
                    self.canvas.delete(elem['img_id'])
                if 'selection_id' in elem:
                    self.canvas.delete(elem['selection_id'])
                self.step_elements.pop(i)
                self.selected_step_id = None
                self.status_var.set("Step deleted")
                break

    def get_canvas_coords(self, event):
        """Get canvas coordinates accounting for scroll."""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        return x, y
    
    def on_canvas_press(self, event):
        """Handle canvas mouse press."""
        if not self.current_tool:
            return

        cx, cy = self.get_canvas_coords(event)
        # Image-space coordinates (step/text tools operate in image pixels).
        z = self.zoom if self.zoom else 1.0
        ix, iy = cx / z, cy / z

        self.drawing = True
        self.start_x = cx
        self.start_y = cy

        # Handle text tool
        if self.current_tool == 'text':
            # Check if clicking on existing text
            clicked_text = self.find_text_at_position(ix, iy)
            if clicked_text:
                # Select and prepare to drag. The pre-drag snapshot is taken
                # lazily on the first drag motion (see on_canvas_drag) to
                # avoid polluting history with no-op clicks.
                self.select_text_element(clicked_text['id'])
                self.dragging_text = True
                self._drag_snapshot_taken = False
                self.drag_offset_x = ix - clicked_text['x']
                self.drag_offset_y = iy - clicked_text['y']
            else:
                # Add new text
                self.drawing = False
                self.add_text_element(ix, iy)

        # Handle step tool — works at ANY zoom level.
        elif self.current_tool == 'step':
            # Check if clicking on existing step to drag
            clicked_step = self.find_step_at_position(ix, iy)
            if clicked_step:
                self.select_step_element(clicked_step['id'])
                self.dragging_step = True
                self._drag_snapshot_taken = False
                self.drag_step_offset_x = ix - clicked_step['x']
                self.drag_step_offset_y = iy - clicked_step['y']
            else:
                # Add new step (pass image-space coordinates)
                self.drawing = False
                self.add_step_element(ix, iy)
    
    def on_canvas_drag(self, event):
        """Handle canvas mouse drag."""
        # Handle text dragging (elem['x']/['y'] are stored in IMAGE space,
        # while canvas items live in canvas space — so we convert deltas).
        if self.dragging_text and self.selected_text_id is not None:
            # Snapshot the pre-drag state on the first motion event so
            # undo restores the original text position.
            if not getattr(self, '_drag_snapshot_taken', False):
                self.save_state()
                self._drag_snapshot_taken = True

            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z

            for elem in self.text_elements:
                if elem['id'] == self.selected_text_id:
                    new_x = ix - self.drag_offset_x
                    new_y = iy - self.drag_offset_y

                    # Update canvas position (canvas-space)
                    if elem['canvas_id']:
                        self.canvas.coords(
                            elem['canvas_id'], new_x * z, new_y * z
                        )

                    # Update position (image-space)
                    elem['x'] = new_x
                    elem['y'] = new_y

                    # Update cursor position (canvas-space)
                    self.canvas.delete('selection')
                    cursor_x = new_x * z
                    cursor_y1 = new_y * z
                    cursor_y2 = (new_y + elem['height']) * z

                    elem['cursor_id'] = self.canvas.create_line(
                        cursor_x, cursor_y1, cursor_x, cursor_y2,
                        fill='#2196F3',
                        width=2,
                        tags='selection'
                    )
                    break
            return

        # Handle step dragging (step coords are stored in IMAGE space)
        if self.dragging_step and self.selected_step_id is not None:
            # Snapshot the pre-drag state on the first motion event so
            # undo restores the original step position.
            if not getattr(self, '_drag_snapshot_taken', False):
                self.save_state()
                self._drag_snapshot_taken = True

            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            x, y = cx / z, cy / z

            for elem in self.step_elements:
                if elem['id'] == self.selected_step_id:
                    new_x = x - self.drag_step_offset_x
                    new_y = y - self.drag_step_offset_y

                    # Deltas in IMAGE space, converted to canvas space for move().
                    dx = (new_x - elem['x']) * z
                    dy = (new_y - elem['y']) * z

                    if 'img_id' in elem:
                        self.canvas.move(elem['img_id'], dx, dy)
                    if 'selection_id' in elem:
                        self.canvas.move(elem['selection_id'], dx, dy)

                    elem['x'] = new_x
                    elem['y'] = new_y
                    break
            return

        if not self.drawing or not self.current_tool:
            return

        x, y = self.get_canvas_coords(event)

        # Remove previous preview
        if self.current_shape:
            self.canvas.delete(self.current_shape)
            self.current_shape = None

        # Draw preview for step tool
        if self.current_tool == 'step':
            half = self.step_size // 2
            x1, y1 = x - half, y - half
            x2, y2 = x + half, y + half
            
            if self.step_shape == 'circle':
                self.current_shape = self.canvas.create_oval(
                    x1, y1, x2, y2,
                    outline=self.current_color,
                    width=3
                )
            else:  # square
                self.current_shape = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline=self.current_color,
                    width=3
                )
            return

        # Draw preview for arrow tool
        if self.current_tool == 'arrow':
            self.current_shape = self.canvas.create_line(
                self.start_x, self.start_y, x, y,
                fill=self.current_color,
                width=self.stroke_width,
                arrow='both' if self.arrow_heads == 'double' else 'last',
                arrowshape=(
                    self.stroke_width * 4,
                    self.stroke_width * 3,
                    self.stroke_width * 1,
                ),
            )
            return

        # Draw preview for highlight tool
        if self.current_tool == 'highlight':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline=self.current_color,
                fill=self.current_color,
                stipple='gray25',
                width=1,
            )
            return

        # Draw preview for blur tool
        if self.current_tool == 'blur':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline='#FF9800',
                width=2,
                dash=(5, 5),
            )
            return

        # Draw preview shape
        if self.current_tool in ['rectangle', 'circle']:
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'line':
            self.current_shape = self.canvas.create_line(
                self.start_x, self.start_y, x, y,
                fill=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'crop':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline='yellow',
                width=2,
                dash=(5, 5)
            )
        elif self.current_tool == 'text' and self.text_box_mode:
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline='#FF9800',
                width=2,
                dash=(5, 5)
            )
    
    def on_canvas_release(self, event):
        """Handle canvas mouse release."""
        # Handle text release
        if self.dragging_text:
            self.dragging_text = False
            return

        # Handle step release
        if self.dragging_step:
            self.dragging_step = False
            return

        if not self.drawing or not self.current_tool:
            return

        self.drawing = False
        x, y = self.get_canvas_coords(event)

        # Remove preview
        if self.current_shape:
            self.canvas.delete(self.current_shape)
            self.current_shape = None

        # Calculate bounds
        x1 = min(self.start_x, x)
        y1 = min(self.start_y, y)
        x2 = max(self.start_x, x)
        y2 = max(self.start_y, y)
        
        # Minimum size check
        if x2 - x1 < 5 or y2 - y1 < 5:
            return
        
        # Save state for undo (and invalidate redo stack)
        self.save_state()

        # Arrow tool — uses directional start->end, not normalized bounds
        if self.current_tool == 'arrow':
            z = self.zoom if self.zoom else 1.0
            ax1, ay1 = self.start_x / z, self.start_y / z
            ax2, ay2 = x / z, y / z
            # Skip if arrow is too short
            length = math.hypot(ax2 - ax1, ay2 - ay1)
            if length < 5:
                return
            draw = ImageDraw.Draw(self.image)
            self._draw_arrow_on_image(
                draw, ax1, ay1, ax2, ay2,
                self.current_color, self.stroke_width,
                self.arrow_style, self.arrow_heads,
            )
            self.refresh_display()
            return

        # Convert canvas coords to image coords (divide by zoom).
        z = self.zoom if self.zoom else 1.0
        ix1, iy1 = x1 / z, y1 / z
        ix2, iy2 = x2 / z, y2 / z

        # Draw shape on image
        draw = ImageDraw.Draw(self.image)

        if self.current_tool == 'rectangle':
            draw.rectangle(
                [ix1, iy1, ix2, iy2],
                outline=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'line':
            draw.line(
                [(ix1, iy1), (ix2, iy2)],
                fill=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'circle':
            draw.ellipse(
                [ix1, iy1, ix2, iy2],
                outline=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'crop':
            # Crop the image
            self.image = self.image.crop((int(ix1), int(iy1), int(ix2), int(iy2)))
            self.refresh_display()
            return
        elif self.current_tool == 'highlight':
            region = self.image.crop((int(ix1), int(iy1), int(ix2), int(iy2)))
            overlay = Image.new('RGBA', region.size, self.current_color)
            overlay.putalpha(89)
            if region.mode != 'RGBA':
                region = region.convert('RGBA')
            region = Image.alpha_composite(region, overlay)
            self.image.paste(region.convert('RGB'), (int(ix1), int(iy1)))
        elif self.current_tool == 'blur':
            region = self.image.crop((int(ix1), int(iy1), int(ix2), int(iy2)))
            if self.blur_mode == 'pixelate':
                bs = max(1, self.blur_intensity)
                small_w = max(1, region.width // bs)
                small_h = max(1, region.height // bs)
                region = region.resize((small_w, small_h), Image.NEAREST)
                region = region.resize((int(ix2) - int(ix1), int(iy2) - int(iy1)), Image.NEAREST)
            else:
                from PIL import ImageFilter
                region = region.filter(ImageFilter.GaussianBlur(radius=self.blur_intensity))
            self.image.paste(region, (int(ix1), int(iy1)))

        self.refresh_display()

    def on_canvas_motion(self, event):
        """Handle mouse motion for hover cursor feedback."""
        if self.dragging_text or self.dragging_step or self.drawing:
            return

        x, y = self.get_canvas_coords(event)

        # Check if hovering over a step
        if self.current_tool == 'step':
            hovered = self.find_step_at_position(x, y)
            if hovered:
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="")
        else:
            self.canvas.config(cursor="")

    def on_canvas_double_click(self, event):
        """Handle double-click to edit text."""
        cx, cy = self.get_canvas_coords(event)
        z = self.zoom if self.zoom else 1.0
        x, y = cx / z, cy / z
        
        # Find text at position
        clicked_text = self.find_text_at_position(x, y)
        if clicked_text:
            # Prompt for new text
            new_text = self.prompt_text(clicked_text['text'])
            if new_text and new_text != clicked_text['text']:
                # Snapshot before mutation so undo can restore the old text.
                self.save_state()
                # Update text
                clicked_text['text'] = new_text
                
                # Recreate on canvas
                if clicked_text['canvas_id']:
                    self.canvas.delete(clicked_text['canvas_id'])
                
                z = self.zoom if self.zoom else 1.0
                clicked_text['canvas_id'] = self.canvas.create_text(
                    clicked_text['x'] * z, clicked_text['y'] * z,
                    text=new_text,
                    fill=clicked_text['color'],
                    font=(clicked_text['font_family'],
                          max(1, int(round(clicked_text['font_size'] * z)))),
                    anchor='nw'
                )

                # Update dimensions (stored in image space)
                try:
                    from PIL import ImageFont
                    font = ImageFont.truetype(f"{clicked_text['font_family'].lower().replace(' ', '')}.ttf", clicked_text['font_size'])
                except:
                    font = ImageFont.truetype("arial.ttf", clicked_text['font_size'])

                temp_img = Image.new('RGB', (1, 1))
                draw = ImageDraw.Draw(temp_img)
                bbox = draw.textbbox((0, 0), new_text, font=font)
                clicked_text['width'] = bbox[2] - bbox[0]
                clicked_text['height'] = bbox[3] - bbox[1]

                # Update cursor position (canvas-space)
                self.canvas.delete('selection')
                cursor_x = clicked_text['x'] * z
                cursor_y1 = clicked_text['y'] * z
                cursor_y2 = (clicked_text['y'] + clicked_text['height']) * z
                
                clicked_text['cursor_id'] = self.canvas.create_line(
                    cursor_x, cursor_y1, cursor_x, cursor_y2,
                    fill='#2196F3',
                    width=2,
                    tags='selection'
                )
                
                self.status_var.set(f"Text updated: '{new_text}'")
    
    def refresh_display(self):
        """Refresh the canvas display with current image at current zoom.

        Delete + recreate the canvas image, then lower it to the bottom of
        the z-stack so that deferred-rendered overlays (step images, text
        items, selection borders, preview shapes) remain visible above the
        background. The dot-grid items re-lower themselves when drawn. If
        the zoom level has changed since the last refresh, also re-render
        every step/text overlay so they track the zoomed background.
        """
        if abs(self.zoom - 1.0) < 1e-6:
            display_source = self.image
        else:
            new_w = max(1, int(round(self.image.width * self.zoom)))
            new_h = max(1, int(round(self.image.height * self.zoom)))
            resample = Image.LANCZOS if self.zoom < 1.0 else Image.NEAREST
            display_source = self.image.resize((new_w, new_h), resample)

        self.display_image = ImageTk.PhotoImage(display_source)
        if getattr(self, 'image_id', None):
            try:
                self.canvas.delete(self.image_id)
            except Exception:
                pass
        self.image_id = self.canvas.create_image(
            0, 0, image=self.display_image, anchor='nw'
        )
        # Lower the background image below all annotation overlays so
        # canvas-only step/text/selection items stay visible after redraws,
        # then re-lower the grid so it stays underneath the image.
        self.canvas.tag_lower(self.image_id)
        self.canvas.tag_lower('grid')
        self.canvas.config(
            scrollregion=(0, 0, display_source.width, display_source.height)
        )

        # Reposition/rescale overlays when zoom changes. We only re-render
        # the expensive step photos when the zoom actually changed, to
        # avoid flooding refresh_display calls (e.g. after every shape
        # draw) with unnecessary supersampled renders.
        last_zoom = getattr(self, '_last_overlay_zoom', None)
        if last_zoom is None or abs(last_zoom - self.zoom) > 1e-6:
            self._sync_overlays_to_zoom()
            self._last_overlay_zoom = self.zoom

    def _sync_overlays_to_zoom(self):
        """Re-render and reposition all step/text overlays at the current
        zoom level. Called from refresh_display whenever zoom changes."""
        z = self.zoom if self.zoom else 1.0

        # Steps: re-render the PhotoImage at the zoomed size and place the
        # canvas item at canvas-space coordinates.
        for elem in self.step_elements:
            if 'img_id' in elem:
                try:
                    self.canvas.delete(elem['img_id'])
                except Exception:
                    pass
            photo, _, _ = self._render_step_image(elem, zoom=z)
            elem['photo'] = photo
            elem['img_id'] = self.canvas.create_image(
                elem['x'] * z, elem['y'] * z, image=photo, anchor='nw'
            )
            # Rebuild the selection border if this step is selected.
            if 'selection_id' in elem:
                try:
                    self.canvas.delete(elem['selection_id'])
                except Exception:
                    pass
                pad = 4
                elem['selection_id'] = self.canvas.create_rectangle(
                    (elem['x'] - pad) * z, (elem['y'] - pad) * z,
                    (elem['x'] + elem['width'] + pad) * z,
                    (elem['y'] + elem['height'] + pad) * z,
                    outline=Theme.PRIMARY, width=2, dash=(4, 4),
                    tags='selection'
                )

        # Text: recreate each canvas text item at canvas-space coords with
        # a zoom-scaled font. Also rebuild the selection cursor if shown.
        for elem in self.text_elements:
            if elem.get('canvas_id'):
                try:
                    self.canvas.delete(elem['canvas_id'])
                except Exception:
                    pass
            elem['canvas_id'] = self.canvas.create_text(
                elem['x'] * z, elem['y'] * z,
                text=elem['text'],
                fill=elem['color'],
                font=(elem['font_family'],
                      max(1, int(round(elem['font_size'] * z)))),
                anchor='nw'
            )
            if 'cursor_id' in elem:
                try:
                    self.canvas.delete(elem['cursor_id'])
                except Exception:
                    pass
                elem['cursor_id'] = self.canvas.create_line(
                    elem['x'] * z, elem['y'] * z,
                    elem['x'] * z, (elem['y'] + elem['height']) * z,
                    fill='#2196F3', width=2, tags='selection'
                )

    def on_scroll_vertical(self, event):
        """Plain wheel pans the canvas vertically. Never zooms."""
        if getattr(event, 'delta', 0) == 0:
            return 'break'
        # If Ctrl is held, defer to the zoom handler and do nothing here.
        # (state bit 0x4 = Control on Windows.)
        if getattr(event, 'state', 0) & 0x4:
            return 'break'
        self.canvas.yview_scroll(int(-event.delta / 120), 'units')
        return 'break'

    def on_scroll_horizontal(self, event):
        """Shift+wheel pans the canvas horizontally. Never zooms."""
        if getattr(event, 'delta', 0) == 0:
            return 'break'
        self.canvas.xview_scroll(int(-event.delta / 120), 'units')
        return 'break'

    def on_mousewheel(self, event):
        """Zoom in/out around the cursor. ONLY fires on Ctrl + mouse wheel."""
        if getattr(event, 'delta', 0) == 0:
            return 'break'
        factor = 1.25 if event.delta > 0 else 0.8
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-6:
            return 'break'

        # Anchor: keep the image pixel under the cursor anchored there.
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        img_x = cx / self.zoom if self.zoom else 0
        img_y = cy / self.zoom if self.zoom else 0

        self.zoom = new_zoom
        self.refresh_display()

        # Re-scroll so (img_x, img_y) lines up with the same cursor position.
        new_cx = img_x * self.zoom
        new_cy = img_y * self.zoom
        total_w = self.image.width * self.zoom
        total_h = self.image.height * self.zoom
        if total_w > 0:
            self.canvas.xview_moveto(max(0.0, (new_cx - event.x) / total_w))
        if total_h > 0:
            self.canvas.yview_moveto(max(0.0, (new_cy - event.y) / total_h))

        self.status_var.set(f"Zoom: {int(self.zoom * 100)}%")
        return 'break'
    
    def render_annotations_to_image(self):
        """Render all text and step elements to the image before saving."""
        # Deselect all text first to remove selection boxes
        self.deselect_all()

        # Render text elements
        draw = ImageDraw.Draw(self.image)
        for elem in self.text_elements:
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(f"{elem['font_family'].lower().replace(' ', '')}.ttf", elem['font_size'])
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", elem['font_size'])
                except:
                    font = ImageFont.load_default()
            draw.text((elem['x'], elem['y']), elem['text'], fill=elem['color'], font=font)

        # Render step elements with supersampled quality
        if not self.step_elements:
            return

        from PIL import ImageFilter

        # Teardrop polygon helper (same as in add_step_element)
        def get_poly_pts(origin_x, origin_y, scale, off_x=0, off_y=0):
            pts = []
            p0, p1, p2, p3 = (50, 10), (100, 10), (135, 50), (135, 50)
            for i in range(21):
                t = i / 20.0
                px = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                py = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            p0, p1, p2, p3 = (135, 50), (135, 50), (100, 90), (50, 90)
            for i in range(1, 21):
                t = i / 20.0
                px = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                py = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            for i in range(1, 41):
                angle = math.pi/2 + (i / 40.0) * math.pi
                px = 50 + 40 * math.cos(angle)
                py = 50 + 40 * math.sin(angle)
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            return pts

        shadow_offset_x = 2
        shadow_offset_y = 4
        shadow_blur_radius = 8
        shadow_alpha = 140
        SS = 4
        pad = 26

        img_w, img_h = self.image.size

        for elem in self.step_elements:
            x_pos = elem['x']
            y_pos = elem['y']
            rect_width = elem['width']
            rect_height = elem['height']
            step_size = elem['size']
            shape = elem['shape']
            fill_color = elem['color']
            text_color = elem.get('text_color', 'white')
            step_num = elem['number']

            # Parse fill color
            if isinstance(fill_color, str) and fill_color.startswith('#'):
                r = int(fill_color[1:3], 16)
                g = int(fill_color[3:5], 16)
                b = int(fill_color[5:7], 16)
                fill_color = (r, g, b, 255)

            left = max(0, int(x_pos - pad))
            top = max(0, int(y_pos - pad))
            right = min(img_w, int(x_pos + rect_width + shadow_offset_x + pad) + 1)
            bottom = min(img_h, int(y_pos + rect_height + shadow_offset_y + pad) + 1)
            tile_w = right - left
            tile_h = bottom - top

            if tile_w <= 0 or tile_h <= 0:
                continue

            ss_size = (tile_w * SS, tile_h * SS)
            mx_img = x_pos - left
            my_img = y_pos - top
            mx = mx_img * SS
            my = my_img * SS
            sox = shadow_offset_x * SS
            soy = shadow_offset_y * SS
            ss_w = rect_width * SS
            ss_h = rect_height * SS
            shadow_rgba = (0, 0, 0, shadow_alpha)

            shadow_layer = Image.new('RGBA', ss_size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_layer)
            shape_layer = Image.new('RGBA', ss_size, (0, 0, 0, 0))
            shape_draw = ImageDraw.Draw(shape_layer)

            if shape == 'circle':
                shadow_draw.ellipse([mx + sox, my + soy, mx + ss_w + sox, my + ss_h + soy], fill=shadow_rgba)
                shape_draw.ellipse([mx, my, mx + ss_w, my + ss_h], fill=fill_color)
            elif shape == 'square':
                shadow_draw.rounded_rectangle([mx + sox, my + soy, mx + ss_w + sox, my + ss_h + soy], radius=6*SS, fill=shadow_rgba)
                shape_draw.rounded_rectangle([mx, my, mx + ss_w, my + ss_h], radius=6*SS, fill=fill_color)
            elif shape == 'rounded_rect':
                radius_ss = (int(rect_height) // 2) * SS
                shadow_draw.rounded_rectangle([mx + sox, my + soy, mx + ss_w + sox, my + ss_h + soy], radius=radius_ss, fill=shadow_rgba)
                shape_draw.rounded_rectangle([mx, my, mx + ss_w, my + ss_h], radius=radius_ss, fill=fill_color)
            elif shape == 'teardrop':
                ss_scale = (step_size * SS) / 100.0
                shadow_draw.polygon(get_poly_pts(mx, my, ss_scale, sox, soy), fill=shadow_rgba)
                shape_draw.polygon(get_poly_pts(mx, my, ss_scale), fill=fill_color)

            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur_radius * SS))
            
            # Apply rotation to shape layer only (not the text)
            rotation = elem.get('rotation', 0)
            if rotation and rotation % 360 != 0 and shape == 'teardrop':
                # Rotate only the shape layer around its center
                shape_layer = shape_layer.rotate(-rotation, resample=Image.BICUBIC, expand=True, center=(ss_w/2, ss_h/2))
                # Adjust shadow position for expanded shape layer
                new_ss_w = shape_layer.width
                new_ss_h = shape_layer.height
                # Recreate shadow layer with same dimensions as rotated shape
                shadow_layer_expanded = Image.new('RGBA', (new_ss_w, new_ss_h), (0, 0, 0, 0))
                # Paste original shadow at offset to match shape position
                offset_x = (new_ss_w - ss_w) // 2
                offset_y = (new_ss_h - ss_h) // 2
                shadow_layer_expanded.paste(shadow_layer, (offset_x, offset_y))
                # Composite
                tile = Image.alpha_composite(shadow_layer_expanded, shape_layer)
            else:
                tile = Image.alpha_composite(shadow_layer, shape_layer)
            
            tile = tile.resize((tile_w, tile_h), Image.LANCZOS)

            # Draw number on tile (will NOT be rotated)
            try:
                from PIL import ImageFont
                font = None
                for f in ["segoeuib.ttf", "arialbd.ttf", "Verdana_Bold.ttf"]:
                    try:
                        font = ImageFont.truetype(f, max(8, int(round(step_size * 0.47))))
                        break
                    except: continue
                if not font:
                    font = ImageFont.truetype("arial.ttf", max(8, int(round(step_size * 0.47))))
            except:
                font = ImageFont.load_default()

            tile_draw = ImageDraw.Draw(tile)
            tile_draw.text((tile_w / 2, tile_h / 2), str(step_num), fill=text_color, font=font, anchor="mm")

            # Composite onto main image
            base = self.image.convert('RGBA')
            ox = left
            oy = top
            base.alpha_composite(tile, dest=(ox, oy))
            self.image = base.convert('RGB')
    
    # ------------------------------------------------------------------
    # Undo / redo
    #
    # History entries are full logical snapshots of the editor state:
    #   {'image': PIL.Image, 'text_elements': [...], 'step_elements': [...],
    #    'step_counter': int}
    #
    # Shape tools (rectangle/line/circle/crop) burn pixels into self.image,
    # but the step and text tools live purely as canvas overlays until
    # render_annotations_to_image() bakes them in at save time. A plain
    # self.image snapshot therefore misses every step/text mutation, which
    # is why the old undo/redo appeared to do nothing. The snapshot model
    # below captures the element lists too and rebuilds the canvas overlays
    # on restore.
    # ------------------------------------------------------------------

    _TEXT_SNAPSHOT_FIELDS = (
        'id', 'text', 'x', 'y', 'color',
        'font_family', 'font_size', 'width', 'height',
    )
    _STEP_SNAPSHOT_FIELDS = (
        'id', 'number', 'x', 'y', 'size', 'width', 'height',
        'shape', 'color', 'text_color', 'rotation',
    )

    def _snapshot_text_elements(self):
        """Return a list of dicts containing only the logical (non-canvas)
        fields of each text element, safe to deep-copy for undo history."""
        return [
            {k: elem[k] for k in self._TEXT_SNAPSHOT_FIELDS if k in elem}
            for elem in self.text_elements
        ]

    def _snapshot_step_elements(self):
        """Return a list of dicts containing only the logical (non-canvas)
        fields of each step element, safe to deep-copy for undo history."""
        return [
            {k: elem[k] for k in self._STEP_SNAPSHOT_FIELDS if k in elem}
            for elem in self.step_elements
        ]

    def _snapshot_state(self):
        """Capture the full editor state as a dict."""
        return {
            'image': self.image.copy(),
            'text_elements': self._snapshot_text_elements(),
            'step_elements': self._snapshot_step_elements(),
            'step_counter': self.step_counter,
        }

    def save_state(self):
        """Push the current editor state onto the undo history and invalidate
        the redo stack. Call this BEFORE any mutation that should be undoable."""
        self.history.append(self._snapshot_state())
        self.redo_stack.clear()
        # Cap the history at a sensible size to keep memory bounded.
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def _clear_overlay_canvas_items(self):
        """Delete all canvas items belonging to step/text overlays and drop
        the stale ids/photo refs from the element dicts. Leaves the element
        lists themselves untouched."""
        for elem in self.text_elements:
            cid = elem.get('canvas_id')
            if cid is not None:
                try:
                    self.canvas.delete(cid)
                except Exception:
                    pass
            elem['canvas_id'] = None
            if 'cursor_id' in elem:
                try:
                    self.canvas.delete(elem['cursor_id'])
                except Exception:
                    pass
                del elem['cursor_id']
        for elem in self.step_elements:
            if 'img_id' in elem:
                try:
                    self.canvas.delete(elem['img_id'])
                except Exception:
                    pass
                del elem['img_id']
            if 'selection_id' in elem:
                try:
                    self.canvas.delete(elem['selection_id'])
                except Exception:
                    pass
                del elem['selection_id']
            if 'photo' in elem:
                del elem['photo']
        # Remove any leftover selection visuals (cursors / dashed borders).
        try:
            self.canvas.delete('selection')
        except Exception:
            pass

    def _apply_state(self, state):
        """Restore a snapshot produced by _snapshot_state()."""
        # Drop all existing overlay canvas items before we swap the element
        # lists, otherwise they become orphaned on the canvas.
        self._clear_overlay_canvas_items()
        self.selected_text_id = None
        self.selected_step_id = None

        self.image = state['image'].copy()
        # Deep-enough copy: the snapshot dicts only contain primitives.
        self.text_elements = [dict(e) for e in state['text_elements']]
        for e in self.text_elements:
            e['canvas_id'] = None
        self.step_elements = [dict(e) for e in state['step_elements']]
        self.step_counter = state['step_counter']

        # Redraw the background image at the current zoom and force a
        # rebuild of every text / step overlay from the restored lists.
        self.refresh_display()
        self._sync_overlays_to_zoom()
        self._last_overlay_zoom = self.zoom

    def undo(self, event=None):
        """Undo the last action (Ctrl+Z)."""
        if not self.history:
            self.status_var.set("Nothing to undo")
            return

        # Push current state onto the redo stack before reverting.
        self.redo_stack.append(self._snapshot_state())
        self._apply_state(self.history.pop())
        self.status_var.set(f"Undo ({len(self.history)} remaining)")

    def redo(self, event=None):
        """Redo the last undone action (Ctrl+Y)."""
        if not self.redo_stack:
            self.status_var.set("Nothing to redo")
            return

        # Push current state back onto history for future undo.
        self.history.append(self._snapshot_state())
        self._apply_state(self.redo_stack.pop())
        self.status_var.set(f"Redo ({len(self.redo_stack)} remaining)")
    
    def auto_save_on_open(self):
        """Auto-save image when editor opens, if enabled in settings."""
        try:
            save_dir = self.settings.get('default_save_path', '')
            if not save_dir:
                self.status_var.set("Auto-save: No default folder configured")
                return
            
            # Create directory if it doesn't exist
            if not os.path.exists(save_dir):
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    print(f"Created directory: {save_dir}")
                except Exception as e:
                    self.status_var.set(f"Auto-save failed: Cannot create directory {save_dir}")
                    print(f"Failed to create directory: {e}")
                    return
            
            # Render text elements to image before saving
            self.render_annotations_to_image()
            
            # Generate filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            format_ext = self.settings.get('image_format', 'png')
            filename = f"screensnap_{timestamp}.{format_ext}"
            file_path = os.path.join(save_dir, filename)
            
            # Save image
            self.image.save(file_path)
            self.last_saved_path = file_path
            print(f"Auto-saved: {file_path}")
            
            # Copy path to clipboard if enabled
            if self.settings.get('auto_copy_path', True):
                abs_path = os.path.abspath(file_path)
                try:
                    pyperclip.copy(abs_path)
                    self.status_var.set(f"✓ Auto-saved & path copied to clipboard")
                    print(f"Path copied to clipboard: {abs_path}")
                except Exception as clip_error:
                    self.status_var.set(f"✓ Auto-saved (clipboard failed: {clip_error})")
                    print(f"Failed to copy to clipboard: {clip_error}")
            else:
                self.status_var.set(f"✓ Auto-saved: {file_path}")
            
            # Show success message
            messagebox.showinfo(
                "Auto-Save Success",
                f"Screenshot saved to:\n{file_path}\n\nPath copied to clipboard!"
            )
            
        except Exception as e:
            error_msg = f"Auto-save failed: {e}"
            self.status_var.set(error_msg)
            print(error_msg)
            messagebox.showerror("Auto-Save Error", error_msg)
    
    def save(self, event=None):
        """Save the image via file dialog."""
        # Render text elements to image before saving
        self.render_annotations_to_image()

        file_path = filedialog.asksaveasfilename(
            title="Save Screenshot",
            defaultextension=".png",
            filetypes=[
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg"),
                ("BMP files", "*.bmp"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            try:
                self.image.save(file_path)
                self.last_saved_path = file_path
                # Also update the library copy if this image originated from library
                if self.library_path and os.path.exists(self.library_path):
                    self.image.save(self.library_path)
                self.status_var.set(f"Saved: {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")
    
    def save_and_copy(self):
        """Save the image and copy path to clipboard."""
        # Render text elements to image before saving
        self.render_annotations_to_image()

        # If we have a last saved path, use it
        if self.last_saved_path:
            file_path = self.last_saved_path
        else:
            # Auto-generate filename based on timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fmt = self.settings.get('image_format', 'png')
            ext = f".{fmt}"
            filename = f"screensnap_{timestamp}{ext}"

            # Determine save directory: use default_save_path if set, else current directory
            save_dir = self.settings.get('default_save_path', '')
            if not save_dir or not os.path.isdir(save_dir):
                save_dir = str(Path.home() / "Pictures")

            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, filename)

        if file_path:
            try:
                self.image.save(file_path)
                self.last_saved_path = file_path

                # Copy absolute path to clipboard
                abs_path = os.path.abspath(file_path)
                pyperclip.copy(abs_path)

                self.status_var.set(f"Saved & copied to clipboard: {abs_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")

    def share_to_imgbb(self):
        """Upload image to ImgBB and copy link to clipboard."""
        # Render text elements to image before uploading
        self.render_annotations_to_image()

        api_key = self.settings.get('imbb_api_key', '')
        if not api_key:
            messagebox.showwarning(
                "ImgBB API Key Required",
                "You need an ImgBB API key to use this feature.\n\n"
                "1. Go to imgbb.com/api\n"
                "2. Sign up for a free account\n"
                "3. Copy your API key\n"
                "4. Open Settings and paste it in the ImgBB section"
            )
            return

        self.status_var.set("Uploading to ImgBB...")
        self.root.config(cursor="watch")
        self.root.update()

        try:
            result = upload_to_imgbb(self.image, api_key, auto_delete_seconds=86400)

            if 'error' in result:
                self.status_var.set(f"ImgBB upload failed: {result['error']}")
                messagebox.showerror("Upload Failed", result['error'])
            else:
                url = result['url']
                pyperclip.copy(url)
                self.status_var.set(f"Uploaded to ImgBB — link copied to clipboard")
                messagebox.showinfo(
                    "Upload Successful",
                    f"Image uploaded to ImgBB!\n\n"
                    f"Link: {url}\n\n"
                    f"Auto-deletes in 24 hours.\n"
                    f"Link has been copied to clipboard."
                )
        finally:
            self.root.config(cursor="")


class LibraryBrowser:
    """Browser window for viewing and managing library screenshots with Midnight Architect styling."""

    def __init__(self, parent, settings):
        self.settings = settings
        self._file_paths = []  # Parallel list storing full paths
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("ScreenSnap Library")
        self.dialog.geometry("800x600")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.config(bg=Theme.BACKGROUND)

        # Center dialog
        self.dialog.update_idletasks()
        w, h = 800, 600
        x = (self.dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (h // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        # Main frame
        main_frame = tk.Frame(self.dialog, bg=Theme.BACKGROUND, padx=30, pady=30)
        main_frame.pack(fill='both', expand=True)

        # Header
        tk.Label(main_frame, text="LIBRARY", font=("Segoe UI Bold", 10), 
                 fg=Theme.PRIMARY, bg=Theme.BACKGROUND).pack(anchor='w', pady=(0, 5))
        
        lib_dir = LibraryManager.LIBRARY_DIR()
        tk.Label(main_frame, text=str(lib_dir), font=("Consolas", 8), 
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.BACKGROUND).pack(anchor='w', pady=(0, 20))

        # Buttons row
        btn_frame = tk.Frame(main_frame, bg=Theme.BACKGROUND)
        btn_frame.pack(fill='x', pady=(0, 15))

        ModernButton(btn_frame, text="📂 OPEN FOLDER", variant="secondary", 
                     command=self.open_folder, font=("Segoe UI Bold", 8)).pack(side='left', padx=(0, 10))
        ModernButton(btn_frame, text="🔄 REFRESH", variant="secondary", 
                     command=self.load_library, font=("Segoe UI Bold", 8)).pack(side='left')

        # List area (The "Sunken" Void)
        list_container = tk.Frame(main_frame, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        list_container.pack(fill='both', expand=True)

        self.listbox = tk.Listbox(
            list_container,
            bg=Theme.SURFACE_LOW,
            fg=Theme.ON_SURFACE,
            font=("Consolas", 10),
            selectbackground=Theme.SURFACE_BRIGHT,
            selectforeground=Theme.PRIMARY,
            borderwidth=0,
            highlightthickness=0,
            activestyle='none'
        )
        v_scroll = ttk.Scrollbar(list_container, orient='vertical', command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=v_scroll.set)

        self.listbox.pack(side='left', fill='both', expand=True)
        v_scroll.pack(side='right', fill='y')

        # Double-click to open
        self.listbox.bind('<Double-Button-1>', self.open_selected)
        self.listbox.bind('<Return>', self.open_selected)

        # Bottom buttons
        bottom_frame = tk.Frame(main_frame, bg=Theme.BACKGROUND)
        bottom_frame.pack(fill='x', pady=(20, 0))

        ModernButton(bottom_frame, text="✏️  OPEN IN EDITOR", variant="primary", 
                     command=self.open_selected, width=20).pack(side='left')
        
        ModernButton(bottom_frame, text="🗑 DELETE", variant="danger", 
                     command=self.delete_selected, width=12).pack(side='right', padx=5)
        
        ModernButton(bottom_frame, text="CLOSE", variant="secondary", 
                     command=self.dialog.destroy, width=12).pack(side='right', padx=5)

        # Load library files
        self.load_library()

        # Block until dialog closes
        self.dialog.wait_window()

    def load_library(self):
        """Load and display library files."""
        self.listbox.delete(0, tk.END)
        self._file_paths = []
        files = LibraryManager.list_files()

        if not files:
            self.listbox.insert(tk.END, "(Library is empty — take a screenshot!)")
            self.listbox.itemconfig(0, fg='gray')
            return

        for f in files:
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            size_kb = f.stat().st_size / 1024
            display = f"{f.name}  ({size_kb:.0f} KB, {mtime.strftime('%Y-%m-%d %H:%M')})"
            self.listbox.insert(tk.END, display)
            self._file_paths.append(str(f))

    def open_selected(self, event=None):
        """Open the selected file in the annotation editor."""
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]
        try:
            image = Image.open(file_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            self.dialog.destroy()
            AnnotationEditor(image, self.settings, library_path=file_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image: {e}")

    def delete_selected(self):
        """Delete the selected file."""
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]
        if messagebox.askyesno("Confirm Delete", f"Delete this screenshot?\n\n{os.path.basename(file_path)}"):
            try:
                os.remove(file_path)
                self.load_library()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete: {e}")

    def open_folder(self):
        """Open the library folder in Windows Explorer."""
        lib_dir = LibraryManager.LIBRARY_DIR()
        lib_dir.mkdir(exist_ok=True)
        subprocess.Popen(f'explorer "{lib_dir}"')


def headless_save(mode, save_path):
    """Capture and save without GUI."""
    try:
        if mode == 'full':
            screenshot = capture_all_screens()
        else:
            print("Error: Headless mode only supports 'full' capture")
            sys.exit(1)
        
        # Ensure directory exists
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        screenshot.save(save_path)
        print(f"Screenshot saved to: {save_path}")
        
    except Exception as e:
        print(f"Error: Failed to capture and save: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='ScreenSnap - Portable Screenshot & Annotation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  screensnap                  Open launcher window
  screensnap full             Capture full screen, open editor
  screensnap region           Select region, open editor
  screensnap full --save C:\\output.png   Headless full screen save
        """
    )
    
    parser.add_argument(
        'mode',
        nargs='?',
        choices=['full', 'region'],
        help='Capture mode: full or region'
    )
    
    parser.add_argument(
        '--save',
        metavar='PATH',
        help='Headless mode: save directly to path without GUI'
    )
    
    args = parser.parse_args()
    
    # Headless mode
    if args.save:
        if not args.mode:
            print("Error: --save requires a mode (full)")
            sys.exit(1)
        headless_save(args.mode, args.save)
    else:
        # GUI mode
        launcher = LauncherWindow(mode=args.mode)
        launcher.run()


if __name__ == '__main__':
    main()
