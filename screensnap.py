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
import contextlib
import queue
import time
import types
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

    try:
        import pytesseract
    except ImportError:
        missing.append('pytesseract')

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
import tempfile
import atexit

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


@contextlib.contextmanager
def _physical_dpi_context():
    """Temporarily make the calling thread Per-Monitor V2 DPI aware.

    Inside the block GetSystemMetrics, BitBlt, EnumDisplayMonitors, DWM and UI
    Automation all report true physical pixels regardless of display scaling.
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
        yield
    finally:
        if old_ctx and set_thread_ctx is not None:
            try:
                set_thread_ctx(ctypes.c_void_p(old_ctx))
            except Exception:
                pass


def capture_virtual_screen():
    """Capture all monitors as one uncropped image.

    Returns (image, left, top): the image is in physical pixels and (left, top)
    is the virtual-screen origin in the same space, so a physical screen point
    (x, y) lives at (x - left, y - top) in the image.

    Uses Windows GDI BitBlt directly (the same path used by Windows' built-in
    Print Screen and Snipping Tool). Falls back to Pillow's ImageGrab if
    BitBlt fails for any reason.
    """
    user32 = ctypes.windll.user32
    with _physical_dpi_context():
        left = user32.GetSystemMetrics(76)    # SM_XVIRTUALSCREEN
        top = user32.GetSystemMetrics(77)     # SM_YVIRTUALSCREEN
        width = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        try:
            img = _bitblt_capture(left, top, width, height)
        except Exception:
            # Fall back to Pillow if GDI path fails.
            img = ImageGrab.grab(
                bbox=(left, top, left + width, top + height),
                all_screens=True,
            )
    return img, left, top


def capture_all_screens():
    """Capture all monitors as a single image, matching native Win+PrtScn."""
    img, _, _ = capture_virtual_screen()
    return _autocrop_black(img)


def _autocrop_black(img):
    """Trim fully-black borders from a screenshot (virtual screen dead zones)."""
    from PIL import ImageChops
    # A pixel is "black" if every channel is at or below threshold
    threshold = 5
    r, g, b = img.convert('RGB').split()
    lit = ImageChops.lighter(ImageChops.lighter(r, g), b).point(
        lambda v: 255 if v > threshold else 0
    )
    bbox = lit.getbbox()
    if bbox is None:
        return img  # entirely black — don't crop to nothing
    if bbox == (0, 0, img.width, img.height):
        return img  # nothing to crop
    return img.crop(bbox)


# ── Smart capture: monitors, windows, UI elements ──────────────────
# The region selector can highlight whatever is under the cursor (a monitor,
# a window, or a UI element such as a browser's address bar) and capture it
# with one click. Everything below works in *physical* pixels.

def _enum_monitor_rects():
    """Return {hmonitor: (l, t, r, b)} in the calling thread's DPI space."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = {}
    proc_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)

    def _cb(hmon, _hdc, rect, _lp):
        r = rect.contents
        found[hmon] = (r.left, r.top, r.right, r.bottom)
        return True

    user32.EnumDisplayMonitors(None, None, proc_type(_cb), None)
    return found


class ScreenMap:
    """Maps between the overlay's logical coordinates and physical pixels.

    tkinter runs system-DPI-aware, so on mixed-DPI setups each monitor is
    scaled differently in logical space than in the captured image. Pairing
    every monitor's logical and physical rect lets us convert points per
    monitor instead of assuming one global scale factor.
    """

    def __init__(self):
        self.monitors = []  # [(physical_rect, logical_rect)] sorted left-to-right
        try:
            logical = _enum_monitor_rects()          # process DPI (system aware)
            with _physical_dpi_context():
                physical = _enum_monitor_rects()
            pairs = [(physical[h], logical[h]) for h in physical if h in logical]
            self.monitors = sorted(pairs, key=lambda p: (p[0][0], p[0][1]))
        except Exception:
            self.monitors = []

    @staticmethod
    def _nearest(point, rects):
        x, y = point
        best, best_d = None, None
        for i, (l, t, r, b) in enumerate(rects):
            dx = max(l - x, 0, x - r + 1)
            dy = max(t - y, 0, y - b + 1)
            d = dx * dx + dy * dy
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _convert(self, x, y, src, dst):
        if not self.monitors:
            return x, y
        i = self._nearest((x, y), [m[src] for m in self.monitors])
        s, d = self.monitors[i][src], self.monitors[i][dst]
        sw, sh = max(1, s[2] - s[0]), max(1, s[3] - s[1])
        return (d[0] + (x - s[0]) * (d[2] - d[0]) / sw,
                d[1] + (y - s[1]) * (d[3] - d[1]) / sh)

    def to_physical(self, x, y):
        return self._convert(x, y, 1, 0)

    def to_logical(self, x, y):
        return self._convert(x, y, 0, 1)

    def physical_rects(self):
        return [m[0] for m in self.monitors]

    def monitor_index_at(self, x, y):
        """Index (left-to-right) of the monitor nearest to a physical point."""
        if not self.monitors:
            return None
        return self._nearest((x, y), self.physical_rects())


def list_windows():
    """Visible top-level windows, topmost first, as dicts of hwnd/rect/title.

    Rects are physical pixels (DWM extended frame bounds, so the invisible
    resize border of Windows 10/11 windows is excluded). ScreenSnap's own
    windows, the desktop, and cloaked/minimised windows are skipped.
    """
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    own_pid = os.getpid()
    windows = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, _lp):
        h = ctypes.c_void_p(hwnd)
        if not user32.IsWindowVisible(h) or user32.IsIconic(h):
            return True
        cloaked = wintypes.DWORD(0)
        dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)  # DWMWA_CLOAKED
        if cloaked.value:
            return True
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == own_pid:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value in ('Progman', 'WorkerW'):
            return True  # desktop: let it fall through to the monitor
        rect = wintypes.RECT()
        # DWMWA_EXTENDED_FRAME_BOUNDS
        if dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
            user32.GetWindowRect(h, ctypes.byref(rect))
        if rect.right - rect.left < 4 or rect.bottom - rect.top < 4:
            return True
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, title, 256)
        windows.append({
            'hwnd': hwnd,
            'rect': (rect.left, rect.top, rect.right, rect.bottom),
            'title': title.value,
        })
        return True

    with _physical_dpi_context():
        user32.EnumWindows(proc_type(_cb), None)
    return windows


def _com_call(obj, index, argtypes, *args):
    """Call slot `index` of a COM object's vtable; returns the HRESULT."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    func = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])
    return func(obj, *args)


class _UIAutomation:
    """Minimal ctypes client for Windows UI Automation (no extra packages).

    Only what smart capture needs: descend from a window to the innermost UI
    element under a point. Must be created and used on a single thread, with
    that thread in the physical DPI context.
    """

    # UIA control types we treat as leaves — descending further only finds
    # glyph runs and text nodes, never something worth capturing on its own.
    _LEAF_TYPES = {
        50000, 50002, 50003, 50004, 50005, 50006, 50007, 50011, 50013, 50014,
        50015, 50016, 50019, 50020, 50024, 50029, 50030, 50031, 50035,
    }
    _MAX_DEPTH = 24
    _MAX_SIBLINGS = 300

    def __init__(self):
        import uuid
        from ctypes import wintypes
        self._wintypes = wintypes
        self._ole32 = ctypes.windll.ole32
        self._oleaut32 = ctypes.windll.oleaut32

        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                        ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

        def guid(text):
            u = uuid.UUID(text)
            g = GUID()
            g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
            for i, byte in enumerate(u.bytes[8:]):
                g.d[i] = byte
            return g

        self._ole32.CoInitializeEx(None, 0)  # multithreaded apartment
        self._ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        clsid = guid("ff48dba4-60ef-4201-aa87-54103eef594e")   # CUIAutomation
        iid = guid("30cbe57d-d9d0-452a-ab13-7ac5ac4825ee")     # IUIAutomation
        self._auto = ctypes.c_void_p()
        hr = self._ole32.CoCreateInstance(
            ctypes.byref(clsid), None, 1 | 4, ctypes.byref(iid), ctypes.byref(self._auto))
        if hr != 0 or not self._auto.value:
            raise OSError(f"UI Automation unavailable (HRESULT {hr & 0xFFFFFFFF:#x})")
        self._walker = ctypes.c_void_p()
        # IUIAutomation::get_ControlViewWalker
        if _com_call(self._auto, 14, (ctypes.POINTER(ctypes.c_void_p),),
                     ctypes.byref(self._walker)) != 0 or not self._walker.value:
            raise OSError("UI Automation tree walker unavailable")

    def close(self):
        for obj in (self._walker, self._auto):
            if obj and obj.value:
                _com_call(obj, 2, ())  # IUnknown::Release
        self._ole32.CoUninitialize()

    # -- thin wrappers over the COM vtable slots we use ----------------
    def _release(self, element):
        _com_call(element, 2, ())

    def _element_from_handle(self, hwnd):
        out = ctypes.c_void_p()
        # IUIAutomation::ElementFromHandle
        hr = _com_call(self._auto, 6, (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                       ctypes.c_void_p(hwnd), ctypes.byref(out))
        return out if hr == 0 and out.value else None

    def _walk(self, slot, element):
        """TreeWalker slot 5 = GetLastChildElement, 7 = GetPreviousSiblingElement."""
        out = ctypes.c_void_p()
        hr = _com_call(self._walker, slot,
                       (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                       element, ctypes.byref(out))
        return out if hr == 0 and out.value else None

    def _rect(self, element):
        r = self._wintypes.RECT()
        # IUIAutomationElement::get_CurrentBoundingRectangle
        hr = _com_call(element, 43, (ctypes.POINTER(self._wintypes.RECT),), ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom) if hr == 0 else None

    def _control_type(self, element):
        v = ctypes.c_int(0)
        _com_call(element, 21, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(v))
        return v.value

    def _name(self, element):
        bstr = ctypes.c_void_p()
        hr = _com_call(element, 23, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(bstr))
        if hr != 0 or not bstr.value:
            return ""
        try:
            return ctypes.wstring_at(bstr.value)
        finally:
            self._oleaut32.SysFreeString(ctypes.c_void_p(bstr.value))

    def _deepest(self, parent, x, y, deadline, depth):
        """Longest chain of nested elements under (x, y) below `parent`.

        Every sibling containing the point is explored, not just the topmost:
        Chromium puts empty full-window panes beside the real browser UI, and
        following only the last sibling dead-ends on one of them. Siblings are
        visited last-to-first (topmost first), so ties go to the topmost.
        """
        best = []
        if depth >= self._MAX_DEPTH:
            return best
        child = self._walk(5, parent)
        scanned = 0
        while child is not None:
            if scanned >= self._MAX_SIBLINGS or time.monotonic() > deadline:
                self._release(child)
                break
            scanned += 1
            rect = self._rect(child)
            if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                entry = (rect, self._name(child))
                if self._control_type(child) in self._LEAF_TYPES:
                    sub = []
                else:
                    sub = self._deepest(child, x, y, deadline, depth + 1)
                if 1 + len(sub) > len(best):
                    best = [entry] + sub
            sibling = self._walk(7, child)
            self._release(child)
            child = sibling
        return best

    def chain_at(self, hwnd, x, y, budget=0.5):
        """UI elements under physical point (x, y) inside `hwnd`.

        Returns [(rect, name), ...] ordered outermost to innermost. If the
        time budget runs out, whatever was found so far is returned.
        """
        root = self._element_from_handle(hwnd)
        if root is None:
            return []
        try:
            return self._deepest(root, x, y, time.monotonic() + budget, 0)
        finally:
            self._release(root)


class _UIAWorker(threading.Thread):
    """Runs UI Automation queries off the Tk thread.

    Only the latest request matters: while the cursor is moving, older
    requests are dropped. Results land in `results` as (key, chain).
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.results = queue.SimpleQueue()
        self._cv = threading.Condition()
        self._request = None
        self._stopped = False

    def request(self, key, hwnd, x, y):
        with self._cv:
            self._request = (key, hwnd, x, y)
            self._cv.notify()

    def stop(self):
        with self._cv:
            self._stopped = True
            self._cv.notify()

    def run(self):
        with _physical_dpi_context():
            try:
                uia = _UIAutomation()
            except Exception:
                return  # no UI Automation: window-level capture still works
            try:
                while True:
                    with self._cv:
                        while self._request is None and not self._stopped:
                            self._cv.wait()
                        if self._stopped:
                            return
                        key, hwnd, x, y = self._request
                        self._request = None
                    try:
                        chain = uia.chain_at(hwnd, x, y)
                    except Exception:
                        chain = []
                    self.results.put((key, chain))
            finally:
                uia.close()


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


# ── Cross-process PrtScn coordination ──────────────────────────────
# The launcher registers PrtScn in-process via RegisterHotKey, while the
# external tray monitor (screensnap-printscreen-monitor.py) hooks the same
# key. Both would otherwise fire on one press. To make them mutually
# exclusive, the process that *owns* the in-app hotkey writes its PID to a
# shared marker file. The monitor skips its own handling whenever a live
# owner is present, so the in-app hotkey wins when a ScreenSnap window is
# open and the monitor only acts when none is running.
#
# The marker lives in the temp dir (not next to the exe) so it is reliably
# writable/discoverable regardless of install location (e.g. Program Files).

def hotkey_owner_lockfile():
    """Path to the shared marker identifying the in-app PrtScn hotkey owner."""
    return os.path.join(tempfile.gettempdir(), "screensnap-hotkey-owner.lock")


def monitor_lockfile():
    """Path to the shared marker identifying the live PrtScn monitor.

    Global (temp dir), NOT per-install-directory: a source-run and a
    dist-run ScreenSnap would otherwise each auto-start their own monitor,
    and one PrtScn press would spawn two capture processes.
    """
    return os.path.join(tempfile.gettempdir(), "screensnap-monitor.lock")


def pid_alive(pid):
    """Robust Windows process-liveness check.

    os.kill(pid, 0) is unreliable on Windows (it does not raise for a dead
    PID), so probe via OpenProcess + GetExitCodeProcess instead.
    """
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

    Windows recycles PIDs aggressively, so a bare liveness check on a stale
    PID marker can match an unrelated process — the monitor would then defer
    to a ghost owner and PrtScn would silently go dead until that process
    exits. If the image name can't be read, treat the PID as foreign: a
    double-fire is recoverable, a dead hotkey is not.
    """
    if sys.platform != 'win32':
        return True
    name = _pid_process_name(pid)
    return ('screensnap' in name) or name.startswith('python')


def hotkey_owner_active():
    """True if a live ScreenSnap process currently owns the in-app hotkey."""
    try:
        path = hotkey_owner_lockfile()
        if not os.path.exists(path):
            return False
        with open(path) as f:
            pid = int((f.read().strip() or "0"))
        return pid_alive(pid) and _pid_is_screensnap(pid)
    except Exception:
        return False


def _write_hotkey_owner():
    """Claim ownership of the in-app PrtScn hotkey for this process."""
    try:
        with open(hotkey_owner_lockfile(), "w") as f:
            f.write(str(os.getpid()))
        # The pump thread's finally-cleanup never runs at interpreter exit
        # (daemon thread stuck in GetMessageW), so also clear the marker at
        # process exit — a stale marker mutes the external monitor.
        atexit.register(_clear_hotkey_owner)
    except Exception:
        pass


def _clear_hotkey_owner():
    """Release ownership, but only if the marker still points at us."""
    try:
        path = hotkey_owner_lockfile()
        if os.path.exists(path):
            with open(path) as f:
                pid = int((f.read().strip() or "0"))
            if pid == os.getpid():
                os.remove(path)
    except Exception:
        pass


def _monitor_lock_active(lock_file):
    """True if the monitor lockfile points at a live monitor process.

    os.kill(pid, 0) is NOT a liveness probe on Windows — it sends
    CTRL_C_EVENT and errors out for detached processes, which made a healthy
    monitor look dead. Every launcher start then spawned a duplicate monitor,
    and one PrtScn press fanned out into several overlapping capture
    processes whose windows ended up inside each other's screenshots.
    """
    try:
        lock_file = Path(lock_file)
        if not lock_file.exists():
            return False
        pid = int(lock_file.read_text().strip() or "0")
        return pid_alive(pid) and _pid_is_screensnap(pid)
    except Exception:
        return False


def _hotkey_worker():
    """Background thread: register PrtScn and pump Windows messages."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, _HOTKEY_ID, _MOD_NOREPEAT, _VK_SNAPSHOT):
        # Another process owns PrtScn (OneDrive, Snipping Tool, etc.)
        print("ScreenSnap: could not register PrintScreen hotkey "
              "(another app may own it).", file=sys.stderr)
        return
    # Announce that this process owns the in-app hotkey so the external
    # monitor stays passive and PrtScn does not double-fire.
    _write_hotkey_owner()
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
        _clear_hotkey_owner()


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

# The currently-open AnnotationEditor (if any). While an editor is open the
# launcher root is withdrawn, so the PrtScn hotkey handler needs this to
# replace the editor with a fresh capture instead of going dead — the
# external monitor defers to this process the whole time it owns the hotkey.
_active_editor = None


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


class Icons:
    """Crisp single-colour toolbar icons drawn with Pillow (no image files to ship).

    Each icon is drawn on a 24x24 grid at 4x resolution and downsampled, then
    tinted with the requested colour, so one icon serves the normal, hovered
    and selected states of a button.
    """

    SS = 4          # supersampling factor
    STROKE = 1.9    # line weight on the 24-unit grid
    _cache = {}     # (name, size, color) -> PIL image (root-independent)

    @classmethod
    def render(cls, name, size, color):
        key = (name, size, color)
        img = cls._cache.get(key)
        if img is None:
            img = cls._cache[key] = cls._draw(name, size, color)
        return img

    @classmethod
    def photo(cls, name, size, color):
        return ImageTk.PhotoImage(cls.render(name, size, color))

    @classmethod
    def _draw(cls, name, size, color):
        n = size * cls.SS
        k = n / 24.0
        sw = max(2, round(cls.STROKE * k))
        img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def P(x, y):
            return (x * k, y * k)

        def dot(x, y, r=None):
            r = sw / 2 if r is None else r * k
            d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=color)

        def line(*pts):
            d.line([P(*p) for p in pts], fill=color, width=sw, joint='curve')
            dot(*pts[0])
            dot(*pts[-1])

        def rect(x1, y1, x2, y2, r=0.0):
            d.rounded_rectangle([P(x1, y1), P(x2, y2)], radius=r * k, outline=color, width=sw)

        def ellipse(x1, y1, x2, y2, fill=False):
            d.ellipse([P(x1, y1), P(x2, y2)], fill=color if fill else None,
                      outline=None if fill else color, width=sw)

        def poly(*pts):
            d.polygon([P(*p) for p in pts], fill=color)

        def arc(x1, y1, x2, y2, start, end):
            d.arc([P(x1, y1), P(x2, y2)], start, end, fill=color, width=sw)

        def head(tip, frm, length=6.5, half=3.4, filled=True):
            dx, dy = tip[0] - frm[0], tip[1] - frm[1]
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            bx, by = tip[0] - ux * length, tip[1] - uy * length
            a = (bx - uy * half, by + ux * half)
            b = (bx + uy * half, by - ux * half)
            if filled:
                poly(tip, a, b)
            else:
                line(a, tip, b)

        def dashed(x1, y1, x2, y2, dash=2.4, gap=1.9):
            """Dashed rectangle outline."""
            for (ax, ay, bx, by) in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
                total = math.hypot(bx - ax, by - ay)
                ux, uy = (bx - ax) / total, (by - ay) / total
                pos = 0.0
                while pos < total:
                    end = min(pos + dash, total)
                    line((ax + ux * pos, ay + uy * pos), (ax + ux * end, ay + uy * end))
                    pos += dash + gap

        def droplet(cx, cy, r, tip_y):
            d_tip = cy - tip_y
            phi = math.degrees(math.acos(r / d_tip))
            pts = [(cx, tip_y)]
            a = -90 + phi
            while a <= 270 - phi:
                pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
                a += 6
            pts.append((cx, tip_y))
            line(*pts)

        mirror = False

        if name == 'rectangle':
            rect(4, 5.5, 20, 18.5, r=1.5)
        elif name == 'circle':
            ellipse(3.8, 3.8, 20.2, 20.2)
        elif name == 'line':
            line((5, 19), (19, 5))
        elif name in ('arrow', 'arrow_filled'):
            line((5, 19), (16, 8))
            head((20, 4), (5, 19), length=7.5, half=3.8)
        elif name == 'arrow_open':
            line((5, 19), (19, 5))
            head((19.5, 4.5), (5, 19), length=7.5, half=4.2, filled=False)
        elif name == 'arrow_single':
            line((3.5, 12), (16, 12))
            head((21, 12), (3.5, 12), length=7, half=3.8)
        elif name == 'arrow_double':
            line((8, 12), (16, 12))
            head((22, 12), (8, 12), length=6.5, half=3.6)
            head((2, 12), (16, 12), length=6.5, half=3.6)
        elif name == 'text':
            line((5, 5.5), (19, 5.5))
            line((12, 5.5), (12, 19))
            line((9, 19), (15, 19))
        elif name == 'step':
            cx, cy, r = 10.2, 12, 7.2
            pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                   for a in range(40, 321, 8)]
            line(*pts, (21.8, 12), pts[0])
            line((10.6, 8.4), (10.6, 15.8))
            line((8.7, 10.0), (10.6, 8.4))
        elif name == 'bubble':
            rect(3, 4, 21, 16, r=3.5)
            line((8, 16), (7, 21), (13, 16))
        elif name == 'stamp':
            ellipse(3.5, 3.5, 20.5, 20.5)
            dot(9.2, 10, 1.25)
            dot(14.8, 10, 1.25)
            arc(7.2, 8.2, 16.8, 17.2, 25, 155)
        elif name == 'highlight':
            line((13.5, 3.5), (20.5, 10.5), (12, 19), (5, 12), (13.5, 3.5))
            line((5, 12), (3.5, 15.5))
            line((3, 21.5), (14, 21.5))
        elif name == 'blur':
            droplet(12, 14.6, 6.4, 3.2)
        elif name == 'pixelate':
            cell, gap, x0 = 4.6, 1.2, 4.3
            for row in range(3):
                for col in range(3):
                    x1 = x0 + col * (cell + gap)
                    y1 = x0 + row * (cell + gap)
                    if (row + col) % 2 == 0:
                        d.rectangle([P(x1, y1), P(x1 + cell, y1 + cell)], fill=color)
                    else:
                        d.rectangle([P(x1, y1), P(x1 + cell, y1 + cell)], outline=color,
                                    width=max(2, sw // 2))
        elif name == 'gaussian':
            ellipse(3.8, 3.8, 20.2, 20.2)
            ellipse(8, 8, 16, 16)
            dot(12, 12, 1.4)
        elif name == 'smart_move':
            line((12, 4), (12, 20))
            line((4, 12), (20, 12))
            head((12, 2), (12, 8), length=4.6, half=2.8)
            head((12, 22), (12, 16), length=4.6, half=2.8)
            head((2, 12), (8, 12), length=4.6, half=2.8)
            head((22, 12), (16, 12), length=4.6, half=2.8)
        elif name == 'crop':
            line((7, 2.5), (7, 17), (21.5, 17))
            line((2.5, 7), (17, 7), (17, 21.5))
        elif name in ('undo', 'redo'):
            line((14, 8), (7, 8))
            arc(9, 8, 19, 18, -90, 90)
            line((14, 18), (8, 18))
            poly((3.6, 8), (9.2, 3.8), (9.2, 12.2))
            mirror = name == 'redo'
        elif name == 'copy':
            line((8, 7.5), (8, 4), (20, 4), (20, 16), (16.5, 16))
            rect(4, 8, 16, 21, r=1.8)
        elif name == 'save':
            rect(4, 4, 20, 20, r=2.2)
            rect(8, 4, 16, 9.5)
            rect(7, 14, 17, 20)
        elif name == 'ocr':
            line((3, 8), (3, 3), (8, 3))
            line((16, 3), (21, 3), (21, 8))
            line((21, 16), (21, 21), (16, 21))
            line((8, 21), (3, 21), (3, 16))
            line((8.5, 9), (15.5, 9))
            line((12, 9), (12, 16))
        elif name == 'share':
            line((12, 15), (12, 4))
            line((7.5, 8.2), (12, 3.7), (16.5, 8.2))
            line((4.5, 13), (4.5, 20), (19.5, 20), (19.5, 13))
        elif name == 'region':
            dashed(3.5, 4.5, 16.5, 17)
            poly((12.5, 12), (21.5, 15.5), (17.6, 16.9), (20, 21.2), (17.7, 22.4), (15.3, 18.1), (12.5, 20.6))
        elif name == 'library':
            rect(4, 4, 10.8, 10.8, r=1.2)
            rect(13.2, 4, 20, 10.8, r=1.2)
            rect(4, 13.2, 10.8, 20, r=1.2)
            rect(13.2, 13.2, 20, 20, r=1.2)
        elif name == 'home':
            line((3, 12), (12, 4), (21, 12))
            line((6, 10.5), (6, 20), (18, 20), (18, 10.5))
            line((10, 20), (10, 15), (14, 15), (14, 20))
        elif name == 'check':
            line((4.5, 12.5), (9.5, 17.5), (19.5, 6.5))
        elif name == 'trash':
            line((4, 7), (20, 7))
            line((9, 7), (9, 4), (15, 4), (15, 7))
            line((6, 7), (7, 20), (17, 20), (18, 7))
            line((10.2, 10.5), (10.2, 16.5))
            line((13.8, 10.5), (13.8, 16.5))
        elif name == 'reset':
            arc(5, 5, 19, 19, 40, 330)
            head((19.2, 10.2), (17.4, 6.6), length=5.6, half=3.2)
            mirror = True
        else:
            raise ValueError(f"unknown icon {name!r}")

        img = img.resize((size, size), Image.LANCZOS)
        if mirror:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img


class Tooltip:
    """Hover tooltip for any widget (shown after a short delay)."""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')
        widget.bind('<Destroy>', self._hide, add='+')

    def _schedule(self, _event=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self):
        self._after = None
        if self._tip is not None:
            return
        try:
            tip = tk.Toplevel(self.widget)
            tip.overrideredirect(True)
            tip.attributes('-topmost', True)
            tk.Label(tip, text=self.text, font=("Segoe UI", 9), fg=Theme.ON_SURFACE,
                     bg=Theme.SURFACE_BRIGHT, padx=9, pady=4, highlightthickness=1,
                     highlightbackground=Theme.OUTLINE).pack()
            tip.update_idletasks()
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - tip.winfo_reqwidth() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            x = max(0, min(x, self.widget.winfo_screenwidth() - tip.winfo_reqwidth()))
            tip.geometry(f"+{x}+{y}")
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


class IconButton(ModernButton):
    """Icon-only ModernButton with a tooltip.

    The icon is re-tinted whenever the foreground colour changes, so existing
    code that highlights a button with `btn.config(bg=..., fg=...)` (the active
    tool, toggles) keeps working unchanged. A background set that way becomes
    the button's resting colour, so hovering no longer wipes the highlight.
    """

    def __init__(self, master, icon, tip=None, variant="tool", size=22, **kwargs):
        self._icon = icon
        self._icon_size = size
        self._photo = None
        kwargs.setdefault('padx', 9)
        kwargs.setdefault('pady', 7)
        super().__init__(master, variant=variant, **kwargs)
        self._set_icon(self.cget('fg'))
        self.tooltip = Tooltip(self, tip) if tip else None

    def _set_icon(self, color):
        self._photo = Icons.photo(self._icon, self._icon_size, color)
        tk.Button.configure(self, image=self._photo)

    def configure(self, cnf=None, **kw):
        if cnf is None and not kw:
            return super().configure()
        if cnf:
            kw = {**cnf, **kw}
        result = super().configure(**kw)
        fg = kw.get('fg', kw.get('foreground'))
        if fg is not None:
            self._set_icon(fg)
        bg = kw.get('bg', kw.get('background'))
        if bg is not None:
            self._bg = bg
            self._abg = Theme.PRIMARY_GLOW if bg == Theme.PRIMARY else Theme.SURFACE_BRIGHT
        return result

    config = configure

    # Hover colours are applied directly so they don't overwrite the resting colour.
    def on_enter(self):
        tk.Button.configure(self, bg=self._abg)

    def on_leave(self):
        tk.Button.configure(self, bg=self._bg)


def _clear_root(root):
    """Remove all children from a root without destroying it."""
    for widget in root.winfo_children():
        widget.destroy()
    root.geometry('')
    root.title('')
    root.resizable(True, True)
    root.protocol('WM_DELETE_WINDOW', lambda: root.destroy())


def _dir_writable(dir_path):
    """True if dir_path exists (or can be created) AND is truly writable.

    Probes with a real file write: os.access() is unreliable against
    Windows ACLs, and an installed copy under C:\\Program Files gets
    WinError 5 on any write attempt.
    """
    try:
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        probe = dir_path / f".write-probe-{os.getpid()}"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


class SettingsManager:
    """Manages application settings persistence using INI file."""

    _resolved_config_dir = None  # cached CONFIG_DIR resolution

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
        """Config dir: next to the exe/script when writable (portable mode),
        else %APPDATA%\\ScreenSnap\\config — an installed copy lives under
        C:\\Program Files where writes are denied. Probe-based rather than
        matching "program files" in the path so custom install dirs behave.
        """
        if cls._resolved_config_dir is None:
            candidate = cls._get_base_dir() / "config"
            if _dir_writable(candidate):
                cls._resolved_config_dir = candidate
            else:
                appdata = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
                cls._resolved_config_dir = Path(appdata) / "ScreenSnap" / "config"
        return cls._resolved_config_dir

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
            'printscreen_monitor': 'false',
            'tesseract_path': '',
            'library_view': 'thumbnails',
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
            'printscreen_monitor': str(settings.get('printscreen_monitor', False)).lower(),
            'tesseract_path': settings.get('tesseract_path', ''),
            'library_view': settings.get('library_view', 'thumbnails'),
        }

        try:
            settings_file = cls.SETTINGS_FILE()
            with open(settings_file, 'w') as f:
                config.write(f)
            print(f"Settings saved to: {settings_file}")
        except Exception as e:
            print(f"Failed to save settings: {e}")

        # Storage Location may have changed — re-resolve the library folder
        LibraryManager._resolved_dir = None


class LibraryManager:
    """Manages the screenshot library folder."""

    _resolved_dir = None  # cached LIBRARY_DIR resolution
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}

    @staticmethod
    def _get_base_dir():
        """Get the base directory (works for both .py and .exe)."""
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        else:
            return Path(__file__).parent

    @classmethod
    def LIBRARY_DIR(cls):
        """Resolve the library folder.

        The library IS the user's configured Storage Location
        (default_save_path) when one is set and writable — the Library
        browser must show the same folder captures are saved to. Falls
        back to a 'library' folder next to the exe/script (portable mode),
        then to %LOCALAPPDATA%\\ScreenSnap\\library — user data must never
        require admin rights (the installed copy lives in Program Files).
        """
        if cls._resolved_dir is None:
            configured = ''
            try:
                configured = (SettingsManager.load().get('default_save_path') or '').strip()
            except Exception:
                pass
            portable = cls._get_base_dir() / "library"
            if configured and _dir_writable(configured):
                cls._resolved_dir = Path(configured)
            elif _dir_writable(portable):
                cls._resolved_dir = portable
            else:
                base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
                cls._resolved_dir = Path(base) / 'ScreenSnap' / 'library'
        return cls._resolved_dir

    @classmethod
    def ensure_library(cls):
        """Ensure the library directory exists."""
        lib_dir = cls.LIBRARY_DIR()
        lib_dir.mkdir(parents=True, exist_ok=True)
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
        files = []
        for f in lib_dir.iterdir():
            if f.is_file() and f.suffix.lower() in cls.IMAGE_EXTS:
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


# ── OCR helpers ────────────────────────────────────────────────────
# The installer ships a portable Tesseract under <app>/tesseract/. When
# running from source or the system has Tesseract installed elsewhere, we
# fall back through common locations and PATH.
import shutil


class TesseractNotFoundError(RuntimeError):
    """Raised when the Tesseract binary cannot be located."""


def _bundled_tesseract_path():
    """Path to Tesseract shipped next to ScreenSnap.exe (or the .py file)."""
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return base / "tesseract" / "tesseract.exe"


def find_tesseract(settings=None):
    """Return the absolute path to tesseract.exe, or None if not found.

    Resolution order:
      1. settings['tesseract_path'] if set and pointing to an existing file
      2. <app dir>/tesseract/tesseract.exe (bundled by the installer)
      3. C:\\Program Files\\Tesseract-OCR\\tesseract.exe
      4. C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe
      5. shutil.which('tesseract') (PATH)
    """
    if settings:
        configured = (settings.get('tesseract_path') or '').strip()
        if configured and os.path.isfile(configured):
            return configured

    bundled = _bundled_tesseract_path()
    if bundled.is_file():
        return str(bundled)

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    on_path = shutil.which('tesseract')
    if on_path:
        return on_path

    return None


def run_ocr(image: Image.Image, settings=None) -> str:
    """Run Tesseract OCR on a PIL image. Returns stripped text.

    Raises TesseractNotFoundError if the binary cannot be located.
    Raises pytesseract.TesseractError on runtime failure.
    """
    import pytesseract

    binary = find_tesseract(settings)
    if not binary:
        raise TesseractNotFoundError(
            "Tesseract is not installed or could not be located."
        )
    pytesseract.pytesseract.tesseract_cmd = binary
    text = pytesseract.image_to_string(image, lang='eng')
    return text.strip()


class LauncherWindow:
    """Initial launcher window with Full Screen and Region buttons."""

    def __init__(self, mode=None, save_path=None):
        self.root = _get_root()
        self.settings = SettingsManager.load()

        # Auto-start Print Screen monitor if enabled in settings
        self._auto_start_printscreen_monitor()

        # Handle CLI mode if specified
        self.mode = mode
        self.save_path = save_path

        if mode:
            # CLI/monitor-triggered capture: skip the launcher UI entirely.
            # Building it first flashed the window for ~100ms on every
            # PrtScn press and could bleed it into the frozen capture.
            self.root.withdraw()
            self.root.after(50, self.auto_execute)
        else:
            # Build and show the launcher UI
            self._build_launcher_ui()
    
    def center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        width = 500
        height = 620
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
        elif self.mode == 'display':
            self.execute_region_capture(mode='display')

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

        # Lockfile check — avoids launching duplicates. Must be a real
        # liveness probe (os.kill(pid, 0) sends CTRL_C_EVENT on Windows and
        # misreports detached processes as dead → duplicate monitors).
        lock_file = Path(monitor_lockfile())
        if _monitor_lock_active(lock_file):
            return  # already running

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
        pre-captured image.
        """
        try:
            if screenshot is None:
                screenshot = capture_all_screens()
            # Auto-save to library
            fmt = self.settings.get('image_format', 'png')
            lib_path = LibraryManager.save_to_library(screenshot, fmt)
            self.root.withdraw()
            AnnotationEditor(screenshot, self.settings, library_path=lib_path)
            # Editor closed — if a replacement editor (REGION button / PrtScn
            # while editing) is still open, don't rebuild the launcher over it.
            # Checked live via _active_editor: a one-shot flag would misfire
            # when a replaced editor is later closed via 🏠 LAUNCHER.
            if _active_editor is not None and not _active_editor._closed:
                return
            # Show launcher again
            self._build_launcher_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture screen: {e}")
            self._build_launcher_ui()

    def _build_launcher_ui(self):
        """Build/rebuild the Midnight Architect launcher UI on the root."""
        _clear_root(self.root)
        self.root.deiconify()
        self.root.title("ScreenSnap v1.1")
        self.root.geometry("500x620")
        self.root.resizable(False, False)
        self.root.config(bg=Theme.BACKGROUND)

        # Reload settings so status reflects current state
        self.settings = SettingsManager.load()

        self.center_window()

        main_container = tk.Frame(self.root, bg=Theme.BACKGROUND, padx=30, pady=30)
        main_container.pack(fill='both', expand=True)

        tk.Label(
            main_container,
            text="ScreenSnap",
            font=("Segoe UI Semibold", 28),
            fg=Theme.PRIMARY,
            bg=Theme.BACKGROUND
        ).pack(pady=(5, 0))

        tk.Label(
            main_container,
            text="Midnight Architect Edition",
            font=("Segoe UI", 9, "bold"),
            fg=Theme.ON_SURFACE_VARIANT,
            bg=Theme.BACKGROUND
        ).pack(pady=(0, 40))

        ModernButton(
            main_container,
            variant="success",
            text="📷  FULL SCREEN",
            command=self.capture_full,
            font=("Segoe UI Bold", 11)
        ).pack(fill='x', pady=8)

        ModernButton(
            main_container,
            variant="primary",
            text="✂️  REGION / WINDOW",
            command=self.capture_region,
            font=("Segoe UI Bold", 11)
        ).pack(fill='x', pady=8)

        ModernButton(
            main_container,
            variant="primary",
            text="🖥  SINGLE DISPLAY",
            command=self.capture_display,
            font=("Segoe UI Bold", 11)
        ).pack(fill='x', pady=8)

        ModernButton(
            main_container,
            variant="action",
            text="🔤  CAPTURE TEXT",
            command=self.capture_text,
            font=("Segoe UI Bold", 11)
        ).pack(fill='x', pady=8)

        row_frame = tk.Frame(main_container, bg=Theme.BACKGROUND)
        row_frame.pack(fill='x', pady=20)

        ModernButton(
            row_frame,
            variant="action",
            text="📚 Library",
            command=self.open_library,
            width=15
        ).pack(side='left', expand=True, padx=(0, 5))

        ModernButton(
            row_frame,
            variant="action",
            text="📂 Open File",
            command=self.open_file,
            width=15
        ).pack(side='left', expand=True, padx=(5, 0))

        status_frame = tk.Frame(main_container, bg=Theme.SURFACE, padx=15, pady=15)
        status_frame.pack(fill='x', pady=(20, 0))

        status_color = "#2E7D32" if self.settings.get('auto_save') else Theme.ON_SURFACE_VARIANT
        status_text = "✓ Auto-save active" if self.settings.get('auto_save') else "• Manual mode"

        tk.Label(
            status_frame,
            text=status_text,
            font=("Segoe UI Bold", 9),
            fg=status_color,
            bg=Theme.SURFACE
        ).pack(anchor='w')

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

        ModernButton(
            main_container,
            variant="secondary",
            text="⚙  SYSTEM SETTINGS",
            command=self.open_settings,
            font=("Segoe UI Bold", 10)
        ).pack(fill='x', side='bottom', pady=(20, 0))

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
                # Editor closed — skip the launcher if a replacement editor
                # is still open (see execute_full_capture)
                if _active_editor is not None and not _active_editor._closed:
                    return
                # Show launcher again
                self._build_launcher_ui()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {e}")
                self._build_launcher_ui()

    def capture_display(self):
        """Handle single-display capture from launcher."""
        self.root.withdraw()
        self.root.after(200, lambda: self.execute_region_capture(mode='display'))

    def execute_region_capture(self, mode='region'):
        """Execute region selection (or display picking) and open editor."""
        try:
            # Hide launcher
            self.root.withdraw()

            # Create region selector as overlay
            selector = RegionSelector(self.root, mode=mode)

            if selector.result:
                # Auto-save to library
                fmt = self.settings.get('image_format', 'png')
                lib_path = LibraryManager.save_to_library(selector.result, fmt)
                editor = AnnotationEditor(selector.result, self.settings, library_path=lib_path)

                # Editor closed — skip the launcher if a replacement editor
                # is still open (see execute_full_capture)
                if _active_editor is not None and not _active_editor._closed:
                    return

            # Show launcher again
            self._build_launcher_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select region: {e}")
            self._build_launcher_ui()

    def capture_text(self):
        """Capture a region → run OCR → show preview. Editor is skipped."""
        self.root.withdraw()
        self.root.after(200, self._execute_text_capture)

    def _execute_text_capture(self):
        try:
            selector = RegionSelector(self.root)
            if selector.result:
                self.root.config(cursor="watch")
                self.root.update()
                try:
                    text = run_ocr(selector.result, self.settings)
                except TesseractNotFoundError:
                    self.root.config(cursor="")
                    self._prompt_install_tesseract_launcher()
                    return
                except Exception as e:
                    self.root.config(cursor="")
                    messagebox.showerror("OCR Error", f"Tesseract failed:\n{e}")
                    return
                finally:
                    self.root.config(cursor="")

                copied = False
                if text:
                    try:
                        pyperclip.copy(text)
                        copied = True
                    except Exception:
                        pass
                # Show the launcher again BEFORE the result dialog: it is
                # transient over the root, and a transient of a withdrawn
                # master never appears on Windows.
                self._build_launcher_ui()
                OCRResultDialog(self.root, text, copied=copied)
        except Exception as e:
            messagebox.showerror("Error", f"Text capture failed: {e}")
        finally:
            # Rebuild only if an early return/error left the root hidden
            # (success path already rebuilt above)
            if self.root.state() == 'withdrawn':
                self._build_launcher_ui()

    def _prompt_install_tesseract_launcher(self):
        """Tesseract-missing prompt from the launcher context."""
        INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
        answer = messagebox.askyesno(
            "Tesseract Not Installed",
            "Tesseract is required for OCR but was not found on this machine.\n\n"
            f"Install it from:\n{INSTALL_URL}\n\n"
            "Would you like to browse for an existing tesseract.exe now?"
        )
        if not answer:
            try:
                os.startfile(INSTALL_URL)
            except Exception:
                pass
            return
        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")],
        )
        if path and os.path.isfile(path):
            self.settings['tesseract_path'] = path
            SettingsManager.save(self.settings)

    def open_library(self):
        """Open the library browser."""
        self.root.withdraw()
        self.root.after(100, self._do_open_library)

    def _do_open_library(self):
        """Actually open the library browser."""
        try:
            LibraryBrowser(self.root, self.settings)
            # Show launcher again after browser closes
            self._build_launcher_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open library: {e}")
            self._build_launcher_ui()

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
        """Handle PrtScn by starting a region selection.

        The launcher is hidden and the drag-to-select overlay is shown, matching
        the external monitor's behavior so PrtScn does the same thing whether or
        not a ScreenSnap window is already open.
        """
        try:
            if not self.root.winfo_exists():
                return
            # A modal dialog holds the Tk grab (settings, OCR result, …) —
            # a selector opened now would never receive mouse events and its
            # fullscreen overlay would appear stuck. Ignore the hotkey.
            try:
                if self.root.grab_current() is not None:
                    return
            except Exception:
                pass
            if self.root.state() == 'withdrawn':
                # Root withdrawn = an editor, dialog, or capture is active.
                # If it's an editor, PrtScn must still work: replace it with
                # a fresh region capture (same as its ✂ REGION button).
                # Otherwise ignore the hotkey to avoid re-entrancy.
                ed = _active_editor
                if ed is not None and not ed._closed:
                    ed.capture_new_region()
                return
            self.capture_region()
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

        # 6. OCR Section
        ocr_f = create_section(scrollable_frame, "OCR (Image-to-Text)")
        tk.Label(ocr_f,
                 text="Tesseract path (leave blank to auto-detect)",
                 font=Theme.FONT_LABEL, fg=Theme.ON_SURFACE_VARIANT,
                 bg=Theme.SURFACE).pack(anchor='w', pady=(0, 5))

        self.tesseract_path_var = tk.StringVar(
            value=settings.get('tesseract_path', '')
        )
        tess_entry_f = tk.Frame(ocr_f, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        tess_entry_f.pack(fill='x', pady=(0, 10))
        tk.Entry(tess_entry_f, textvariable=self.tesseract_path_var,
                 font=("Consolas", 9),
                 bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE,
                 insertbackground=Theme.PRIMARY,
                 relief='flat', borderwidth=8).pack(side='left', fill='x', expand=True)

        ModernButton(ocr_f, text="BROWSE tesseract.exe", variant="secondary",
                     command=self.browse_tesseract,
                     font=("Segoe UI Bold", 8)).pack(anchor='e')

        tk.Label(ocr_f,
                 text="Install Tesseract from github.com/UB-Mannheim/tesseract/wiki",
                 font=("Segoe UI", 7), fg=Theme.ON_SURFACE_VARIANT,
                 bg=Theme.SURFACE).pack(anchor='w', pady=(10, 0))

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

    def browse_tesseract(self):
        """Browse for the tesseract.exe binary."""
        file = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")],
        )
        if file:
            self.tesseract_path_var.set(file)

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
        self.settings['tesseract_path'] = self.tesseract_path_var.get()
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
    """Full-screen overlay for region selection with Midnight Architect styling.

    Drag to select a free-form region. Hovering also highlights the display,
    window, or UI element under the cursor (scroll to grow or shrink the
    target) and a click captures it. With mode='display' only whole displays
    are offered.
    """

    CLICK_SLOP = 4         # px of movement before a click becomes a drag
    UIA_DEBOUNCE_MS = 50   # let the cursor settle before querying UI Automation
    SAME_RECT_TOL = 6      # px: UI elements this close to a window's bounds are the window

    def __init__(self, parent, mode='region'):
        self.result = None
        self.mode = mode
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        self.current_bright = None
        self.finished = False
        self.dragging = False

        # Hover-to-capture state. hover_chain holds the candidate targets under
        # the cursor, smallest first, as (physical_rect, label).
        self.hover_chain = []
        self.hover_index = 0
        self.hover_items = []
        self._hover_photo = None
        self._bright_cache = {}
        self._user_scrolled = False
        self._hover_hwnd = None
        self._hover_point = (0, 0)  # last cursor position, physical pixels
        self._uia_chain = []       # UI elements under the cursor, smallest first
        self._uia_worker = None
        self._uia_after = None
        self._request_key = 0
        self._closing = False

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
        self.v_width = width
        self.v_height = height
        self.screen_map = ScreenMap()

        # Freeze the screen BEFORE showing the overlay so subsequent mouse
        # movement / animations don't change what the user sees while selecting.
        # Caller is expected to have hidden (or withdrawn-then-destroyed) its
        # own windows already; give the compositor a couple of frames to
        # actually drop them from the screen before grabbing.
        try:
            parent.update_idletasks()
        except Exception:
            pass
        time.sleep(0.09)
        try:
            self.frozen, self.phys_left, self.phys_top = capture_virtual_screen()
        except Exception as e:
            print(f"Failed to capture frozen screen: {e}")
            self.frozen = None
            self.phys_left, self.phys_top = x, y

        # Snapshot the window stack now, while the overlay doesn't exist yet.
        self.windows = []
        if self.mode == 'region':
            try:
                self.windows = list_windows()
            except Exception as e:
                print(f"Failed to enumerate windows: {e}")

        # Build a display-sized copy (logical pixels) and a dimmed version for
        # the overlay background. Crops come from the original physical-
        # resolution snapshot.
        if self.frozen is not None:
            self.frozen_display = self._build_display_image(width, height)
            dim_layer = Image.new('RGB', (width, height), (0, 0, 0))
            self.dimmed_display = Image.blend(self.frozen_display, dim_layer, 0.5)
        else:
            self.frozen_display = None
            self.dimmed_display = None

        # Create full-screen opaque window (no -alpha so the live screen can't
        # bleed through the selection overlay).
        self.root = tk.Toplevel(parent)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='#000000')
        self.root.config(cursor="crosshair")
        self.root.overrideredirect(True)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Canvas for overlay
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg='#000000')
        self.canvas.pack(fill='both', expand=True)

        # Paint the dimmed frozen snapshot as the canvas background.
        if self.dimmed_display is not None:
            self._dim_tk = ImageTk.PhotoImage(self.dimmed_display)
            self.canvas.create_image(0, 0, anchor='nw', image=self._dim_tk)

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

        # One-line usage hint, dropped after a few seconds or on first use
        if self.mode == 'display':
            hint = "Click a display to capture it   •   Drag for a custom region   •   Esc to cancel"
        else:
            hint = ("Click to capture the highlighted area   •   Drag for a custom region   •   "
                    "Scroll to grow / shrink   •   Esc to cancel")
        self.hint_label = tk.Label(
            self.root,
            text=hint,
            font=("Segoe UI", 10),
            bg=Theme.SURFACE,
            fg=Theme.ON_SURFACE,
            padx=14,
            pady=8
        )
        hint_x, hint_y = self._physical_to_canvas(*self._primary_monitor_top_center())
        self.hint_label.place(x=int(hint_x), y=int(hint_y) + 24, anchor='n')
        self.root.after(6000, self._hide_hint)

        # Bind events
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Motion>', self.on_motion)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self.root.bind('<Escape>', self.on_escape)

        self.root.after(30, self._poll_uia)
        self.root.after(60, self._initial_hover)
        self.root.wait_window()

    # ── Coordinate helpers ─────────────────────────────────────────

    def _build_display_image(self, width, height):
        """The frozen snapshot laid out in the overlay's logical coordinates.

        Monitors are resized one by one so mixed-DPI setups stay undistorted.
        """
        frozen = self.frozen.convert('RGB')
        monitors = self.screen_map.monitors
        if not monitors:
            if frozen.size == (width, height):
                return frozen
            return frozen.resize((width, height), Image.LANCZOS)
        canvas = Image.new('RGB', (width, height), (0, 0, 0))
        for phys, logical in monitors:
            tile = frozen.crop((phys[0] - self.phys_left, phys[1] - self.phys_top,
                                phys[2] - self.phys_left, phys[3] - self.phys_top))
            box = (logical[0] - self.offset_x, logical[1] - self.offset_y,
                   logical[2] - self.offset_x, logical[3] - self.offset_y)
            size = (box[2] - box[0], box[3] - box[1])
            if tile.size != size:
                tile = tile.resize(size, Image.LANCZOS)
            canvas.paste(tile, box[:2])
        return canvas

    def _canvas_to_physical(self, cx, cy):
        return self.screen_map.to_physical(cx + self.offset_x, cy + self.offset_y)

    def _physical_to_canvas(self, px, py):
        lx, ly = self.screen_map.to_logical(px, py)
        return lx - self.offset_x, ly - self.offset_y

    def _primary_monitor_top_center(self):
        """Physical point at the top-centre of the monitor holding the origin."""
        rects = self.screen_map.physical_rects()
        if not rects:
            return (self.phys_left + self.v_width / 2, self.phys_top)
        origin = next((r for r in rects if r[0] <= 0 < r[2] and r[1] <= 0 < r[3]), rects[0])
        return ((origin[0] + origin[2]) / 2, origin[1])

    def _crop_physical(self, rect):
        """Crop the frozen snapshot to a physical-pixel rect, or None if empty."""
        fw, fh = self.frozen.size
        l = max(0, min(fw, int(round(rect[0] - self.phys_left))))
        t = max(0, min(fh, int(round(rect[1] - self.phys_top))))
        r = max(0, min(fw, int(round(rect[2] - self.phys_left))))
        b = max(0, min(fh, int(round(rect[3] - self.phys_top))))
        if r - l < 1 or b - t < 1:
            return None
        return self.frozen.crop((l, t, r, b))

    # ── Hover-to-capture ───────────────────────────────────────────

    def _hide_hint(self):
        try:
            self.hint_label.place_forget()
        except tk.TclError:
            pass

    def _initial_hover(self):
        """Highlight whatever is already under the cursor when the overlay opens."""
        if self._closing:
            return
        try:
            px, py = self.root.winfo_pointerxy()
        except tk.TclError:
            return
        if self.start_x is None:
            self.on_motion(types.SimpleNamespace(x=px - self.offset_x, y=py - self.offset_y))

    def on_motion(self, event):
        # Only fires with no button held; dragging is handled by on_drag.
        # Hover is a convenience on top of drag-select, so a failure here must
        # never leave the overlay stuck or block a normal capture.
        try:
            self._update_hover(event.x, event.y)
        except Exception as e:
            print(f"Hover update failed: {e}")

    def on_wheel(self, event):
        """Scroll up to grow the highlighted target, down to shrink it."""
        if self.start_x is not None or not self.hover_chain:
            return
        step = 1 if event.delta > 0 else -1
        new_index = max(0, min(len(self.hover_chain) - 1, self.hover_index + step))
        if new_index != self.hover_index:
            self.hover_index = new_index
            self._user_scrolled = True
            try:
                self._draw_hover()
            except Exception as e:
                print(f"Hover draw failed: {e}")

    def _window_at(self, px, py):
        for w in self.windows:
            l, t, r, b = w['rect']
            if l <= px < r and t <= py < b:
                return w
        return None

    @staticmethod
    def _near(a, b, tol):
        return all(abs(p - q) <= tol for p, q in zip(a, b))

    def _update_hover(self, cx, cy):
        px, py = self._canvas_to_physical(cx, cy)
        px, py = int(round(px)), int(round(py))
        self._hover_point = (px, py)
        window = self._window_at(px, py) if self.mode == 'region' else None
        hwnd = window['hwnd'] if window else None

        if hwnd != self._hover_hwnd:
            self._hover_hwnd = hwnd
            self._user_scrolled = False
            self._uia_chain = []
        elif self._uia_chain:
            # Still inside the innermost element we already resolved?  Then
            # nothing smaller can be under the cursor, so skip re-querying.
            l, t, r, b = self._uia_chain[0][0]
            if not (l <= px < r and t <= py < b):
                self._uia_chain = []

        if hwnd is not None and not self._uia_chain:
            self._schedule_uia(hwnd, px, py)
        self._rebuild_targets(px, py, window)

    def _rebuild_targets(self, px, py, window):
        """Recompute the candidate targets (smallest first) and redraw if needed."""
        targets = []

        def add(rect, label):
            if rect[2] - rect[0] < 4 or rect[3] - rect[1] < 4:
                return
            if targets and self._near(targets[-1][0], rect, 1):
                return
            targets.append((rect, label))

        if window is not None:
            for rect, name in self._uia_chain:
                if not self._near(rect, window['rect'], self.SAME_RECT_TOL):
                    add(rect, name or "Element")
            add(window['rect'], (window['title'] or "Window")[:48])

        monitors = self.screen_map.physical_rects()
        if monitors:
            index = self.screen_map.monitor_index_at(px, py)
            add(monitors[index], f"Display {index + 1}")
        elif self.frozen is not None:
            add((self.phys_left, self.phys_top,
                 self.phys_left + self.frozen.width, self.phys_top + self.frozen.height),
                "Screen")

        previous = self.hover_chain[self.hover_index] if self.hover_chain else None
        self.hover_chain = targets
        if previous is not None and self._user_scrolled:
            # Keep the level the user scrolled to if it still exists.
            self.hover_index = next(
                (i for i, t in enumerate(targets) if t[0] == previous[0]), 0)
        else:
            self.hover_index = 0
        current = targets[self.hover_index] if targets else None
        if current != previous or not self.hover_items:
            self._draw_hover()

    def _schedule_uia(self, hwnd, px, py):
        if self._uia_after is not None:
            self.root.after_cancel(self._uia_after)
        self._request_key += 1
        key = self._request_key
        self._uia_after = self.root.after(
            self.UIA_DEBOUNCE_MS, lambda: self._send_uia(key, hwnd, px, py))

    def _send_uia(self, key, hwnd, px, py):
        self._uia_after = None
        if self._closing:
            return
        if self._uia_worker is None:
            self._uia_worker = _UIAWorker()
            self._uia_worker.start()
        self._uia_worker.request(key, hwnd, px, py)

    def _poll_uia(self):
        """Pick up the newest UI Automation result from the worker thread."""
        if self._closing:
            return
        try:
            if self._uia_worker is not None and not self.dragging and self.start_x is None:
                latest = None
                while True:
                    try:
                        latest = self._uia_worker.results.get_nowait()
                    except queue.Empty:
                        break
                if latest is not None and latest[0] == self._request_key and latest[1]:
                    # Worker returns outermost-first; targets are smallest-first.
                    self._uia_chain = list(reversed(latest[1]))
                    px, py = self._hover_point
                    self._rebuild_targets(px, py, self._window_at(px, py))
        except Exception as e:
            print(f"Hover refresh failed: {e}")
        finally:
            self.root.after(30, self._poll_uia)

    def _clear_hover(self):
        for item in self.hover_items:
            self.canvas.delete(item)
        self.hover_items = []
        self.dim_label.place_forget()

    def _draw_hover(self):
        """Reveal and outline the selected target, with a size label."""
        self._clear_hover()
        if not self.hover_chain or self.dragging:
            return
        rect, label = self.hover_chain[self.hover_index]
        x1, y1 = self._physical_to_canvas(rect[0], rect[1])
        x2, y2 = self._physical_to_canvas(rect[2], rect[3])
        x1 = max(0, min(self.v_width, int(round(x1))))
        x2 = max(0, min(self.v_width, int(round(x2))))
        y1 = max(0, min(self.v_height, int(round(y1))))
        y2 = max(0, min(self.v_height, int(round(y2))))
        if x2 - x1 < 2 or y2 - y1 < 2:
            return

        if self.frozen_display is not None:
            key = (x1, y1, x2, y2)
            photo = self._bright_cache.get(key)
            if photo is None:
                if len(self._bright_cache) > 32:
                    self._bright_cache.clear()
                photo = ImageTk.PhotoImage(self.frozen_display.crop(key))
                self._bright_cache[key] = photo
            self._hover_photo = photo  # keep alive even if the cache is cleared
            self.hover_items.append(
                self.canvas.create_image(x1, y1, anchor='nw', image=photo))
        self.hover_items.append(self.canvas.create_rectangle(
            x1, y1, x2, y2, outline=Theme.PRIMARY, width=3))

        self.dim_label.config(text=f"{label}  ·  {rect[2] - rect[0]} × {rect[3] - rect[1]}")
        self.dim_label.update_idletasks()
        label_h = self.dim_label.winfo_reqheight()
        # Above the target if there is room, otherwise tucked inside its top-left.
        label_y = y1 - label_h - 6 if y1 - label_h - 6 >= 0 else y1 + 6
        self.dim_label.place(x=max(0, min(x1, self.v_width - 40)), y=label_y)

    # ── Mouse handling ─────────────────────────────────────────────

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.dragging = False
        if self.current_rect:
            self.canvas.delete(self.current_rect)
            self.current_rect = None
        if self.current_bright:
            self.canvas.delete(self.current_bright)
            self.current_bright = None

    def on_drag(self, event):
        if self.start_x is None: return
        if not self.dragging:
            if (abs(event.x - self.start_x) < self.CLICK_SLOP
                    and abs(event.y - self.start_y) < self.CLICK_SLOP):
                return  # still a click; keep the hover highlight
            self.dragging = True
            self._clear_hover()
            self._hide_hint()
        if self.current_rect:
            self.canvas.delete(self.current_rect)
        if self.current_bright:
            self.canvas.delete(self.current_bright)
            self.current_bright = None

        cx1 = max(0, min(self.v_width, min(self.start_x, event.x)))
        cy1 = max(0, min(self.v_height, min(self.start_y, event.y)))
        cx2 = max(0, min(self.v_width, max(self.start_x, event.x)))
        cy2 = max(0, min(self.v_height, max(self.start_y, event.y)))

        # Reveal the un-dimmed patch of the frozen snapshot inside the selection
        if self.frozen_display is not None and cx2 > cx1 and cy2 > cy1:
            bright_crop = self.frozen_display.crop((cx1, cy1, cx2, cy2))
            self._bright_tk = ImageTk.PhotoImage(bright_crop)
            self.current_bright = self.canvas.create_image(
                cx1, cy1, anchor='nw', image=self._bright_tk
            )

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

        if not self.dragging:
            # A click: capture whatever is highlighted (no highlight = cancel).
            if self.hover_chain and self.frozen is not None:
                self.result = self._crop_physical(self.hover_chain[self.hover_index][0])
            self._close()
            return

        # Calculate canvas-relative region
        cx1 = min(self.start_x, event.x)
        cy1 = min(self.start_y, event.y)
        cx2 = max(self.start_x, event.x)
        cy2 = max(self.start_y, event.y)

        # Clamp to the virtual screen
        cx1 = max(0, min(self.v_width, cx1))
        cx2 = max(0, min(self.v_width, cx2))
        cy1 = max(0, min(self.v_height, cy1))
        cy2 = max(0, min(self.v_height, cy2))

        # Minimum size check
        if cx2 - cx1 < 10 or cy2 - cy1 < 10:
            self._close()
            return

        # Crop from the frozen snapshot (preserves its physical resolution).
        # Fall back to a live grab only if the freeze step failed earlier.
        if self.frozen is not None:
            x1, y1 = self._canvas_to_physical(cx1, cy1)
            x2, y2 = self._canvas_to_physical(cx2, cy2)
            try:
                self.result = self._crop_physical((x1, y1, x2, y2))
            except Exception as e:
                print(f"Failed to crop region: {e}")
        else:
            # Fallback: hide overlay and grab the live screen
            x1 = cx1 + self.offset_x
            y1 = cy1 + self.offset_y
            x2 = cx2 + self.offset_x
            y2 = cy2 + self.offset_y
            self.root.withdraw()
            self.root.update_idletasks()
            time.sleep(0.05)
            try:
                self.result = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
            except Exception as e:
                print(f"Failed to capture region: {e}")

        self._close()

    def on_escape(self, event):
        """Handle ESC key."""
        self.result = None
        self._close()

    def _close(self):
        """Tear down the overlay and stop the UI Automation worker."""
        self._closing = True
        if self._uia_worker is not None:
            self._uia_worker.stop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


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
        '#000000',  # Black
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

        # Stamp tool properties
        self.stamp_size = 40
        self.stamp_selected = None       # filepath of selected stamp
        self.stamp_categories = {}       # {category_name: [filepath, ...]}
        self._stamp_cache = {}           # {(filepath, render_size): PIL.Image}
        self._stamps_dir = self._get_stamps_dir()
        self.stamp_elements = []
        self.stamp_counter = 0
        self.selected_stamp_id = None
        self.dragging_stamp = False
        self.drag_stamp_offset_x = 0
        self.drag_stamp_offset_y = 0

        # Shape elements (deferred rendering for rectangle, circle, line, arrow, highlight)
        self.shape_elements = []
        self.shape_counter = 0
        self.selected_shape_id = None
        self.dragging_shape = False
        self.drag_shape_offset_x = 0
        self.drag_shape_offset_y = 0

        # Bubble tool properties
        self.bubble_elements = []
        self.selected_bubble_id = None
        self.dragging_bubble = False
        self.drag_bubble_offset_x = 0
        self.drag_bubble_offset_y = 0
        self.dragging_bubble_anchor = False
        self.dragging_bubble_resize = False
        self.bubble_resize_corner = None  # 'br', 'bl', 'tr', 'tl'
        self.bubble_counter = 0

        # Smart move tool state
        self.smart_move_phase = 'select'  # 'select' or 'move'
        self.smart_move_region = None     # (x1, y1, x2, y2) image coords
        self.smart_move_snapshot = None   # Image copy of selected region
        self.smart_move_preview_ids = []  # Canvas item IDs for preview
        self.dragging_smart_move = False
        self.smart_move_drag_start_x = 0
        self.smart_move_drag_start_y = 0

        # Use the shared app root as a Toplevel
        master = _get_root()
        _clear_root(master)
        self.root = tk.Toplevel(master)
        self.root.title("ScreenSnap - Annotation Editor")
        self.root.state('zoomed')
        self.root.config(bg=Theme.BACKGROUND)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._closed = False
        global _active_editor
        _active_editor = self

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

        IconButton(self.text_props_frame, 'check', tip="Apply text changes", variant="primary",
                   command=self.update_selected_text).pack(side='left', padx=5)
        IconButton(self.text_props_frame, 'trash', tip="Delete selected text", variant="danger",
                   command=self.delete_selected_text).pack(side='left', padx=5)

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

        IconButton(self.step_props_frame, 'reset', tip="Reset step counter to 1", variant="secondary",
                   command=self.reset_step_counter).pack(side='left', padx=5)

        # Arrow properties panel
        self.arrow_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.arrow_props_frame.pack(side='top', fill='x')
        self.arrow_props_frame.pack_forget()

        tk.Label(self.arrow_props_frame, text="ARROW TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.arrow_props_frame, text="Style", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.arrow_filled_btn = IconButton(
            self.arrow_props_frame, 'arrow_filled', tip="Filled arrow head", variant="primary",
            command=lambda: self._set_arrow_style('filled'))
        self.arrow_filled_btn.pack(side='left', padx=2)

        self.arrow_open_btn = IconButton(
            self.arrow_props_frame, 'arrow_open', tip="Open arrow head", variant="tool",
            command=lambda: self._set_arrow_style('open'))
        self.arrow_open_btn.pack(side='left', padx=(2, 20))

        tk.Label(self.arrow_props_frame, text="Heads", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.arrow_single_btn = IconButton(
            self.arrow_props_frame, 'arrow_single', tip="Head at one end", variant="primary",
            command=lambda: self._set_arrow_heads('single'))
        self.arrow_single_btn.pack(side='left', padx=2)

        self.arrow_double_btn = IconButton(
            self.arrow_props_frame, 'arrow_double', tip="Heads at both ends", variant="tool",
            command=lambda: self._set_arrow_heads('double'))
        self.arrow_double_btn.pack(side='left', padx=2)

        # Blur properties panel
        self.blur_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.blur_props_frame.pack(side='top', fill='x')
        self.blur_props_frame.pack_forget()

        tk.Label(self.blur_props_frame, text="BLUR TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.blur_props_frame, text="Mode", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.blur_pixelate_btn = IconButton(
            self.blur_props_frame, 'pixelate', tip="Pixelate", variant="primary",
            command=lambda: self._set_blur_mode('pixelate'))
        self.blur_pixelate_btn.pack(side='left', padx=2)

        self.blur_gaussian_btn = IconButton(
            self.blur_props_frame, 'gaussian', tip="Gaussian blur", variant="tool",
            command=lambda: self._set_blur_mode('gaussian'))
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

        # Stamp properties panel
        self.stamp_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.stamp_props_frame.pack(side='top', fill='x')
        self.stamp_props_frame.pack_forget()

        tk.Label(self.stamp_props_frame, text="STAMP TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 10))

        tk.Label(self.stamp_props_frame, text="Category", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.stamp_category_var = tk.StringVar(value='')
        self.stamp_cat_combo = ttk.Combobox(self.stamp_props_frame, textvariable=self.stamp_category_var,
                                            values=[], state='readonly', width=10)
        self.stamp_cat_combo.pack(side='left', padx=(0, 10))
        self.stamp_cat_combo.bind('<<ComboboxSelected>>', lambda e: self._update_stamp_buttons())

        self.stamp_btn_frame = tk.Frame(self.stamp_props_frame, bg=Theme.SURFACE)
        self.stamp_btn_frame.pack(side='left', padx=(0, 10))
        self._stamp_buttons = []

        tk.Label(self.stamp_props_frame, text="Size", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.stamp_size_var = tk.IntVar(value=40)
        stamp_size_spin = ttk.Spinbox(self.stamp_props_frame, from_=20, to=120,
                                      textvariable=self.stamp_size_var, width=5,
                                      command=lambda: setattr(self, 'stamp_size', self.stamp_size_var.get()))
        stamp_size_spin.pack(side='left')

        # Bubble properties panel
        self.bubble_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.bubble_props_frame.pack(side='top', fill='x')
        self.bubble_props_frame.pack_forget()

        tk.Label(self.bubble_props_frame, text="BUBBLE TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.bubble_props_frame, text="Font Size", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.bubble_font_size_var = tk.IntVar(value=14)
        ttk.Spinbox(self.bubble_props_frame, from_=8, to=48,
                    textvariable=self.bubble_font_size_var, width=5).pack(side='left', padx=(0, 20))

        IconButton(self.bubble_props_frame, 'trash', tip="Delete selected bubble", variant="danger",
                   command=self._delete_selected_bubble).pack(side='left', padx=5)

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
        self.root.bind('<Control-l>', self.open_library)
        self.root.bind('<Control-L>', self.open_library)
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

    def _close_window(self, hide_first=False):
        """Tear down this editor window and release the active-editor slot.

        hide_first withdraws before destroying: destroying a *visible* window
        plays DWM's ~200ms close-fade animation, so a screen grab taken right
        after would catch this editor half-faded over the desktop (ghost UI
        baked into the capture). A hidden window is destroyed with no
        animation.
        """
        global _active_editor
        self._closed = True
        if _active_editor is self:
            _active_editor = None
        if hide_first:
            try:
                self.root.withdraw()
                self.root.update_idletasks()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _on_close(self):
        """Handle window close."""
        self._close_window()
    
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
        """Create the professional Midnight Architect toolbar.

        Two-row layout: tools/colors on top, actions on a dedicated row below
        so action buttons stay visible on smaller screens where everything
        wouldn't fit in a single row.
        """
        container = tk.Frame(parent, bg=Theme.BACKGROUND)

        toolbar = tk.Frame(container, bg=Theme.SURFACE, padx=20, pady=12)
        toolbar.pack(side='top', fill='x')

        # 1. Tools Group — icon buttons; hover for the name and shortcut
        tools_frame = tk.Frame(toolbar, bg=Theme.SURFACE)
        tools_frame.pack(side='left')

        tools = [
            ('rectangle', "Rectangle (R)"),
            ('circle', "Circle (C)"),
            ('line', "Line (L)"),
            ('arrow', "Arrow (A)"),
            ('text', "Text (T)"),
            ('step', "Step number (P)"),
            ('bubble', "Speech bubble (B)"),
            ('stamp', "Stamp (M)"),
            ('highlight', "Highlight (H)"),
            ('blur', "Blur / pixelate (U)"),
            ('smart_move', "Smart move (V)"),
            ('crop', "Crop (X)"),
        ]
        self._tool_names = [t for t, _ in tools]
        # Tools whose keyboard shortcut is live (the rest show "Coming soon")
        self._implemented_overflow = {'arrow', 'highlight', 'blur', 'stamp', 'bubble', 'smart_move'}

        for tool, tip in tools:
            btn = IconButton(tools_frame, tool, tip=tip, command=lambda t=tool: self.set_tool(t))
            btn.pack(side='left', padx=1)
            setattr(self, f'{tool}_btn', btn)

        tk.Frame(toolbar, width=1, bg=Theme.OUTLINE).pack(side='left', fill='y', padx=20)

        # 1b. History Group (Undo / Redo — Quick Access)
        history_frame = tk.Frame(toolbar, bg=Theme.SURFACE)
        history_frame.pack(side='left')

        self.undo_btn = IconButton(
            history_frame, 'undo', tip="Undo (Ctrl+Z)",
            command=self.undo,
        )
        self.undo_btn.pack(side='left', padx=2)

        self.redo_btn = IconButton(
            history_frame, 'redo', tip="Redo (Ctrl+Y)",
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

        # Custom color picker button
        self._custom_color_btn = tk.Button(
            toolbar, text="+", width=3, height=1, relief='flat', borderwidth=1,
            bg=Theme.SURFACE, fg=Theme.ON_SURFACE, cursor='hand2',
            font=("Segoe UI Bold", 9),
            command=self._pick_custom_color,
        )
        self._custom_color_btn.pack(side='left', padx=2)

        # 3. Actions Group — own row so buttons stay visible on smaller screens
        actions_bar = tk.Frame(container, bg=Theme.SURFACE, padx=20, pady=8)
        actions_bar.pack(side='top', fill='x', pady=(2, 0))

        actions_frame = tk.Frame(actions_bar, bg=Theme.SURFACE)
        actions_frame.pack(anchor='center')

        # Packed right-to-left, so they read: share, save, OCR, copy, region, library, launcher
        actions = [
            ('home', "Back to launcher", 'tool', self.back_to_launcher),
            ('library', "Library (Ctrl+L)", 'tool', self.open_library),
            ('region', "New region capture (PrtScn)", 'tool', self.capture_new_region),
            ('copy', "Copy image to clipboard", 'tool', self.copy_image_to_clipboard),
            ('ocr', "OCR: copy text from the image", 'tool', self.ocr_current_image),
            ('save', "Save & copy path", 'success', self.save_and_copy),
            ('share', "Share (upload to ImgBB)", 'tool', self.share_to_imgbb),
        ]
        for icon, tip, variant, command in actions:
            IconButton(actions_frame, icon, tip=tip, variant=variant, size=24,
                       command=command).pack(side='right', padx=3)

        return container
    def capture_new_full(self):
        """Capture full screen and open in a new editor window."""
        # Hide-then-destroy so DWM's close-fade can't ghost this editor
        # into the new capture
        self._close_window(hide_first=True)

        # Give the compositor a beat to actually drop the old window from
        # the screen before grabbing it.
        import time
        time.sleep(0.15)

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
        # Hide-then-destroy so DWM's close-fade can't ghost this editor
        # into the frozen selection snapshot
        self._close_window(hide_first=True)

        # Create region selector (its settle delay covers the compositor
        # dropping the old editor window before the screen is frozen)
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

    def _has_annotations(self):
        """True when this editor holds edits that opening another image would discard."""
        return bool(self.history or self.text_elements or self.step_elements
                    or self.stamp_elements or self.shape_elements or self.bubble_elements)

    def open_library(self, event=None):
        """Browse the library and open the picked image in a fresh editor."""
        browser = LibraryBrowser(self.root, self.settings, pick_only=True)
        path = browser.selected_path
        if not path:
            return
        if self._has_annotations() and not messagebox.askyesno(
                "Discard Annotations?",
                "Opening another image closes this editor and discards any "
                "annotations you haven't saved.\n\nOpen the library image anyway?"):
            return
        try:
            with Image.open(path) as opened:
                image = opened.convert('RGB')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image: {e}")
            return
        self._close_window()
        AnnotationEditor(image, self.settings, library_path=path)

    def back_to_launcher(self):
        """Close editor and return to launcher."""
        self._close_window()
        # No editor left open — the capture flow that created this editor
        # rebuilds the launcher when it unwinds
    
    def set_tool(self, tool):
        """Set the current drawing tool with Midnight Architect styling."""
        # Reset smart_move state when switching away
        if hasattr(self, 'smart_move_phase') and self.current_tool == 'smart_move' and tool != 'smart_move':
            self.smart_move_phase = 'select'
            self.smart_move_region = None
            self.smart_move_snapshot = None
            for cid in getattr(self, 'smart_move_preview_ids', []):
                try:
                    self.canvas.delete(cid)
                except:
                    pass
            self.smart_move_preview_ids = []

        self.current_tool = tool
        self.status_var.set(f"MODE: {tool.upper()}")

        # Highlight the active tool's icon button
        for t in self._tool_names:
            btn = getattr(self, f'{t}_btn', None)
            if btn:
                if t == tool:
                    btn.config(bg=Theme.PRIMARY, fg="#000000")
                else:
                    btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

        # Show/hide properties panels
        if tool == 'text':
            self.text_props_frame.pack(side='top', fill='x')
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.stamp_props_frame.pack_forget()
            self.bubble_props_frame.pack_forget()
        elif tool == 'step':
            self.step_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.stamp_props_frame.pack_forget()
            self.bubble_props_frame.pack_forget()
        elif tool == 'arrow':
            self.arrow_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.stamp_props_frame.pack_forget()
            self.bubble_props_frame.pack_forget()
        elif tool == 'blur':
            self.blur_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.stamp_props_frame.pack_forget()
            self.bubble_props_frame.pack_forget()
        elif tool == 'stamp':
            self.stamp_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.bubble_props_frame.pack_forget()
            # Scan stamps folder and populate category dropdown
            self._scan_stamps()
            categories = list(self.stamp_categories.keys())
            self.stamp_cat_combo['values'] = categories
            if categories:
                if self.stamp_category_var.get() not in categories:
                    self.stamp_category_var.set(categories[0])
                self._update_stamp_buttons()
            else:
                self.status_var.set("No stamps found — add .svg/.png files to stamps/ subfolders")
        elif tool == 'bubble':
            self.bubble_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.stamp_props_frame.pack_forget()
        else:
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.blur_props_frame.pack_forget()
            self.stamp_props_frame.pack_forget()
            self.bubble_props_frame.pack_forget()
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

    @staticmethod
    def _get_stamps_dir():
        """Return the stamps directory path (next to script or EXE)."""
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).parent
        return base / 'stamps'

    def _scan_stamps(self):
        """Scan the stamps directory and populate self.stamp_categories."""
        self.stamp_categories.clear()
        stamps_dir = self._stamps_dir
        if not stamps_dir.is_dir():
            return

        valid_exts = {'.svg', '.png', '.jpg', '.jpeg', '.bmp', '.gif'}
        for subdir in sorted(stamps_dir.iterdir()):
            if not subdir.is_dir():
                continue
            files = []
            for f in sorted(subdir.iterdir()):
                if f.suffix.lower() in valid_exts:
                    files.append(f)
            if files:
                self.stamp_categories[subdir.name] = files

    def _load_stamp_image(self, filepath, render_size):
        """Load a stamp file as a PIL RGBA Image at the given size. Cached."""
        cache_key = (str(filepath), render_size)
        if cache_key in self._stamp_cache:
            return self._stamp_cache[cache_key]

        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        if ext == '.svg':
            img = self._render_svg(filepath, render_size)
        else:
            img = Image.open(filepath).convert('RGBA')
            img = img.resize((render_size, render_size), Image.LANCZOS)

        self._stamp_cache[cache_key] = img
        return img

    @staticmethod
    def _render_svg(filepath, render_size):
        """Render a simple SVG to a PIL RGBA Image using xml.etree + ImageDraw.

        Supports: circle, ellipse, rect, line, polyline, polygon, text.
        This is intentionally minimal — handles the stamp icon SVGs shipped
        with ScreenSnap, not arbitrary SVGs.
        """
        import xml.etree.ElementTree as ET

        ns = '{http://www.w3.org/2000/svg}'
        tree = ET.parse(filepath)
        root = tree.getroot()

        # Parse viewBox or width/height for coordinate scaling
        vb = root.get('viewBox')
        if vb:
            parts = vb.replace(',', ' ').split()
            vb_w, vb_h = float(parts[2]), float(parts[3])
        else:
            vb_w = float(root.get('width', '40'))
            vb_h = float(root.get('height', '40'))

        scale = render_size / max(vb_w, vb_h)

        img = Image.new('RGBA', (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        def sc(v):
            """Scale a coordinate value."""
            return v * scale

        def parse_color(c):
            """Parse a CSS color string."""
            if not c or c == 'none':
                return None
            return c

        def parse_float(s, default=0):
            try:
                return float(s)
            except (TypeError, ValueError):
                return default

        for elem in root.iter():
            tag = elem.tag.replace(ns, '')
            fill = parse_color(elem.get('fill'))
            stroke = parse_color(elem.get('stroke'))
            stroke_w = max(1, int(sc(parse_float(elem.get('stroke-width'), 1))))

            if tag == 'circle':
                cx = sc(parse_float(elem.get('cx')))
                cy = sc(parse_float(elem.get('cy')))
                r = sc(parse_float(elem.get('r')))
                if fill and fill != 'none':
                    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=fill)
                if stroke and stroke != 'none':
                    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=stroke, width=stroke_w)

            elif tag == 'ellipse':
                cx = sc(parse_float(elem.get('cx')))
                cy = sc(parse_float(elem.get('cy')))
                rx = sc(parse_float(elem.get('rx')))
                ry = sc(parse_float(elem.get('ry')))
                if fill and fill != 'none':
                    draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=fill)
                if stroke and stroke != 'none':
                    draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], outline=stroke, width=stroke_w)

            elif tag == 'rect':
                x = sc(parse_float(elem.get('x')))
                y = sc(parse_float(elem.get('y')))
                w = sc(parse_float(elem.get('width')))
                h = sc(parse_float(elem.get('height')))
                if fill and fill != 'none':
                    draw.rectangle([x, y, x+w, y+h], fill=fill)
                if stroke and stroke != 'none':
                    draw.rectangle([x, y, x+w, y+h], outline=stroke, width=stroke_w)

            elif tag == 'line':
                x1 = sc(parse_float(elem.get('x1')))
                y1 = sc(parse_float(elem.get('y1')))
                x2 = sc(parse_float(elem.get('x2')))
                y2 = sc(parse_float(elem.get('y2')))
                color = stroke or fill or '#000'
                draw.line([(x1, y1), (x2, y2)], fill=color, width=stroke_w)

            elif tag in ('polyline', 'polygon'):
                pts_str = elem.get('points', '')
                coords = pts_str.replace(',', ' ').split()
                points = []
                for i in range(0, len(coords) - 1, 2):
                    points.append((sc(float(coords[i])), sc(float(coords[i+1]))))
                if len(points) < 2:
                    continue
                if tag == 'polygon':
                    if fill and fill != 'none':
                        draw.polygon(points, fill=fill)
                    if stroke and stroke != 'none':
                        draw.polygon(points, outline=stroke)
                else:
                    # polyline — draw as connected lines
                    color = stroke or fill or '#000'
                    for i in range(len(points) - 1):
                        draw.line([points[i], points[i+1]], fill=color, width=stroke_w)

            elif tag == 'text':
                x = sc(parse_float(elem.get('x')))
                y = sc(parse_float(elem.get('y')))
                text_content = (elem.text or '').strip()
                if not text_content:
                    continue
                color = fill or '#000'
                font_size = int(sc(parse_float(elem.get('font-size', '16'))))
                try:
                    from PIL import ImageFont
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
                # Handle text-anchor: SVG y is the baseline, not top
                text_anchor = elem.get('text-anchor', 'start')
                if text_anchor == 'middle':
                    # anchor="ms" = middle-x, baseline-y (matches SVG semantics)
                    draw.text((x, y), text_content, fill=color, font=font, anchor="ms")
                elif text_anchor == 'end':
                    draw.text((x, y), text_content, fill=color, font=font, anchor="rs")
                else:
                    draw.text((x, y), text_content, fill=color, font=font, anchor="ls")

        return img

    def _update_stamp_buttons(self):
        """Rebuild stamp selection buttons for the current category."""
        for btn in self._stamp_buttons:
            btn.destroy()
        self._stamp_buttons.clear()

        category = self.stamp_category_var.get()
        files = self.stamp_categories.get(category, [])
        for filepath in files:
            display = filepath.stem.replace('-', ' ').replace('_', ' ').title()
            btn = ModernButton(
                self.stamp_btn_frame,
                text=display,
                variant="primary" if filepath == self.stamp_selected else "tool",
                command=lambda f=filepath: self._select_stamp(f),
                font=("Segoe UI Bold", 8),
            )
            btn.pack(side='left', padx=1)
            self._stamp_buttons.append(btn)

        # Auto-select first stamp if none selected
        if files and (self.stamp_selected is None or self.stamp_selected not in files):
            self.stamp_selected = files[0]
            self._update_stamp_buttons()

    def _select_stamp(self, filepath):
        """Select a stamp file from the library."""
        self.stamp_selected = filepath
        self._update_stamp_buttons()

    def _place_stamp(self, ix, iy):
        """Place the selected stamp at image coordinates with shadow (deferred rendering)."""
        if self.stamp_selected is None:
            self.status_var.set("No stamp selected")
            return

        size = self.stamp_size
        SS = 4
        big_size = size * SS

        stamp_img = self._load_stamp_image(self.stamp_selected, big_size)

        from PIL import ImageFilter
        shadow_off = max(1, SS)
        shadow_tile = Image.new('RGBA', (big_size, big_size), (0, 0, 0, 0))
        shadow_shape = stamp_img.copy()
        r, g, b, a = shadow_shape.split()
        shadow_shape = Image.merge('RGBA', (
            a.point(lambda _: 0),
            a.point(lambda _: 0),
            a.point(lambda _: 0),
            a.point(lambda x: x * 140 // 255),
        ))
        shadow_tile.paste(shadow_shape, (shadow_off, shadow_off * 2), shadow_shape)
        shadow_tile = shadow_tile.filter(ImageFilter.GaussianBlur(radius=SS * 2))

        tile = Image.new('RGBA', (big_size, big_size), (0, 0, 0, 0))
        tile = Image.alpha_composite(tile, shadow_tile)
        tile.paste(stamp_img, (0, 0), stamp_img)

        final = tile.resize((size, size), Image.LANCZOS)

        self.stamp_counter += 1
        elem = {
            'id': self.stamp_counter,
            'x': ix,
            'y': iy,
            'filepath': str(self.stamp_selected),
            'size': size,
            'tile': final,
            'canvas_id': None,
            'photo': None,
        }
        self.stamp_elements.append(elem)
        self._render_stamp_canvas(elem)
        self.refresh_display()

    def _render_stamp_canvas(self, elem):
        z = self.zoom if self.zoom else 1.0
        if elem.get('canvas_id'):
            try:
                self.canvas.delete(elem['canvas_id'])
            except Exception:
                pass
        tile = elem['tile']
        display_size = max(1, int(elem['size'] * z))
        display_tile = tile.resize((display_size, display_size), Image.LANCZOS) if abs(z - 1.0) > 0.01 else tile
        photo = ImageTk.PhotoImage(display_tile)
        elem['photo'] = photo
        cx = (elem['x'] - elem['size'] // 2) * z
        cy = (elem['y'] - elem['size'] // 2) * z
        elem['canvas_id'] = self.canvas.create_image(cx, cy, image=photo, anchor='nw')

    def _find_stamp_at(self, x, y):
        for elem in reversed(self.stamp_elements):
            half = elem['size'] // 2
            if (elem['x'] - half <= x <= elem['x'] + half and
                elem['y'] - half <= y <= elem['y'] + half):
                return elem
        return None

    def _render_shape_canvas(self, elem):
        z = self.zoom if self.zoom else 1.0
        if elem.get('canvas_id'):
            try:
                self.canvas.delete(elem['canvas_id'])
            except Exception:
                pass
        t = elem['type']
        if t == 'rectangle':
            elem['canvas_id'] = self.canvas.create_rectangle(
                elem['x1']*z, elem['y1']*z, elem['x2']*z, elem['y2']*z,
                outline=elem['color'], width=elem['stroke_width'])
        elif t == 'circle':
            elem['canvas_id'] = self.canvas.create_oval(
                elem['x1']*z, elem['y1']*z, elem['x2']*z, elem['y2']*z,
                outline=elem['color'], width=elem['stroke_width'])
        elif t == 'line':
            elem['canvas_id'] = self.canvas.create_line(
                elem['x1']*z, elem['y1']*z, elem['x2']*z, elem['y2']*z,
                fill=elem['color'], width=elem['stroke_width'])
        elif t == 'arrow':
            elem['canvas_id'] = self.canvas.create_line(
                elem['x1']*z, elem['y1']*z, elem['x2']*z, elem['y2']*z,
                fill=elem['color'], width=elem['stroke_width'],
                arrow='both' if elem.get('arrow_heads') == 'double' else 'last',
                arrowshape=(elem['stroke_width']*4, elem['stroke_width']*3, elem['stroke_width']*1))
        elif t == 'highlight':
            elem['canvas_id'] = self.canvas.create_rectangle(
                elem['x1']*z, elem['y1']*z, elem['x2']*z, elem['y2']*z,
                outline=elem['color'], fill=elem['color'], stipple='gray25', width=1)

    def _find_shape_at(self, x, y):
        for elem in reversed(self.shape_elements):
            x1, y1, x2, y2 = elem['x1'], elem['y1'], elem['x2'], elem['y2']
            nx1, ny1 = min(x1, x2), min(y1, y2)
            nx2, ny2 = max(x1, x2), max(y1, y2)
            margin = max(8, elem.get('stroke_width', 3) * 2)
            if elem['type'] in ('rectangle', 'circle', 'highlight'):
                if elem['type'] == 'highlight':
                    if nx1 <= x <= nx2 and ny1 <= y <= ny2:
                        return elem
                else:
                    if (nx1 - margin <= x <= nx2 + margin and ny1 - margin <= y <= ny2 + margin):
                        near_left = abs(x - nx1) < margin
                        near_right = abs(x - nx2) < margin
                        near_top = abs(y - ny1) < margin
                        near_bottom = abs(y - ny2) < margin
                        inside_x = nx1 <= x <= nx2
                        inside_y = ny1 <= y <= ny2
                        if (near_left and inside_y) or (near_right and inside_y) or \
                           (near_top and inside_x) or (near_bottom and inside_x):
                            return elem
            elif elem['type'] in ('line', 'arrow'):
                dx, dy = x2 - x1, y2 - y1
                length_sq = dx*dx + dy*dy
                if length_sq == 0:
                    dist = math.hypot(x - x1, y - y1)
                else:
                    t = max(0, min(1, ((x - x1)*dx + (y - y1)*dy) / length_sq))
                    proj_x = x1 + t * dx
                    proj_y = y1 + t * dy
                    dist = math.hypot(x - proj_x, y - proj_y)
                if dist < margin:
                    return elem
        return None

    def _add_bubble(self, anchor_x, anchor_y):
        """Create a new speech bubble at the given anchor point."""
        self.save_state()
        self.bubble_counter += 1
        bx = anchor_x + 60
        by = anchor_y - 50
        font_size = self.bubble_font_size_var.get()

        elem = {
            'id': self.bubble_counter,
            'x': bx, 'y': by,
            'width': 0, 'height': 0,  # 0 = auto-size from text
            'anchor_x': anchor_x, 'anchor_y': anchor_y,
            'text': 'Type here...',
            'color': self.current_color,
            'font_size': font_size,
            'canvas_ids': {},
        }
        self.bubble_elements.append(elem)
        self._render_bubble_canvas(elem)
        self._edit_bubble_text(elem)

    def _bubble_auto_dims(self, elem):
        """Return auto-sized (w, h) based on text content."""
        font_size = elem['font_size']
        text_lines = elem['text'].split('\n')
        char_w = font_size * 0.6
        text_w = max(len(line) for line in text_lines) * char_w + 20
        text_h = len(text_lines) * (font_size + 4) + 16
        return max(text_w, 80), max(text_h, 30)

    def _bubble_dims(self, elem, z=1.0):
        """Return (w, h) for a bubble — uses explicit size if set, else auto."""
        aw, ah = self._bubble_auto_dims(elem)
        w = elem.get('width', 0) or aw
        h = elem.get('height', 0) or ah
        return w, h

    def _render_bubble_canvas(self, elem):
        """Create/update canvas items for a bubble element as a single PIL image."""
        z = self.zoom if self.zoom else 1.0

        for key, cid in elem.get('canvas_ids', {}).items():
            try:
                self.canvas.delete(cid)
            except Exception:
                pass
        elem['canvas_ids'] = {}

        bx_img, by_img = elem['x'], elem['y']
        ax_img, ay_img = elem['anchor_x'], elem['anchor_y']
        text_w, text_h = self._bubble_dims(elem, z=1.0)

        # Bounding box covering body + anchor (image space)
        margin = 4
        min_x = min(bx_img, ax_img) - margin
        min_y = min(by_img, ay_img) - margin
        max_x = max(bx_img + text_w, ax_img) + margin
        max_y = max(by_img + text_h, ay_img) + margin
        tile_w = max(1, int((max_x - min_x) * z))
        tile_h = max(1, int((max_y - min_y) * z))

        # Positions relative to tile origin (in canvas-pixel space)
        bx = (bx_img - min_x) * z
        by = (by_img - min_y) * z
        ax = (ax_img - min_x) * z
        ay = (ay_img - min_y) * z
        tw = text_w * z
        th = text_h * z
        radius = max(4, int(8 * z))

        # Parse fill color
        color = elem['color']
        try:
            cr = int(color[1:3], 16)
            cg = int(color[3:5], 16)
            cb = int(color[5:7], 16)
        except Exception:
            cr, cg, cb = 128, 128, 128
        fill_rgba = (cr, cg, cb, 210)

        tile = Image.new('RGBA', (tile_w, tile_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tile)

        # Tail triangle
        bcx = bx + tw / 2
        bcy = by + th / 2
        dx = ax - bcx
        dy = ay - bcy
        tail_w = max(8 * z, min(20 * z, tw * 0.15))

        if abs(dx) * th > abs(dy) * tw:
            if dx > 0:
                ty = max(by + tail_w, min(by + th - tail_w, ay))
                tail_pts = [(bx + tw, ty - tail_w / 2), (ax, ay), (bx + tw, ty + tail_w / 2)]
            else:
                ty = max(by + tail_w, min(by + th - tail_w, ay))
                tail_pts = [(bx, ty - tail_w / 2), (ax, ay), (bx, ty + tail_w / 2)]
        else:
            if dy > 0:
                tx = max(bx + tail_w, min(bx + tw - tail_w, ax))
                tail_pts = [(tx - tail_w / 2, by + th), (ax, ay), (tx + tail_w / 2, by + th)]
            else:
                tx = max(bx + tail_w, min(bx + tw - tail_w, ax))
                tail_pts = [(tx - tail_w / 2, by), (ax, ay), (tx + tail_w / 2, by)]

        draw.polygon(tail_pts, fill=fill_rgba)

        # Rounded rectangle body (drawn on top of tail so it overlaps seamlessly)
        draw.rounded_rectangle(
            [bx, by, bx + tw, by + th], radius=radius, fill=fill_rgba,
        )

        # Text
        font_size_px = max(1, int(round(elem['font_size'] * z)))
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", font_size_px)
        except Exception:
            font = ImageFont.load_default()
        draw.text((bx + 10 * z, by + 8 * z), elem['text'], fill='white', font=font)

        # Anchor handle (small circle at tail tip)
        handle_r = max(3, int(5 * z))
        draw.ellipse([ax - handle_r, ay - handle_r, ax + handle_r, ay + handle_r],
                     fill=(255, 255, 255, 200), outline=(100, 100, 100, 200))

        # Resize handle (bottom-right corner)
        rx, ry = bx + tw, by + th
        draw.ellipse([rx - handle_r, ry - handle_r, rx + handle_r, ry + handle_r],
                     fill=(255, 255, 255, 200), outline=(100, 100, 100, 200))

        photo = ImageTk.PhotoImage(tile)
        elem['_bubble_photo'] = photo  # prevent GC
        canvas_x = min_x * z
        canvas_y = min_y * z
        elem['canvas_ids']['img'] = self.canvas.create_image(
            canvas_x, canvas_y, image=photo, anchor='nw',
        )

    def _edit_bubble_text(self, elem):
        """Open text editing for a bubble."""
        new_text = self.prompt_text(elem['text'])
        if new_text and new_text != elem['text']:
            elem['text'] = new_text
            self._render_bubble_canvas(elem)

    def _find_bubble_at(self, ix, iy):
        """Find bubble element at image-space position."""
        for elem in reversed(self.bubble_elements):
            w, h = self._bubble_dims(elem)
            if elem['x'] <= ix <= elem['x'] + w and elem['y'] <= iy <= elem['y'] + h:
                return elem
        return None

    def _bubble_hit_test(self, ix, iy):
        """Hit-test bubbles. Returns (elem, zone) or None.
        zone is 'anchor', 'resize', or 'body'."""
        grab_r = 10
        for elem in reversed(self.bubble_elements):
            # Check anchor point first (tail tip)
            if math.hypot(ix - elem['anchor_x'], iy - elem['anchor_y']) < grab_r:
                return (elem, 'anchor')
            # Check resize handle (bottom-right corner)
            w, h = self._bubble_dims(elem)
            brx, bry = elem['x'] + w, elem['y'] + h
            if math.hypot(ix - brx, iy - bry) < grab_r:
                return (elem, 'resize')
            # Check body
            if elem['x'] <= ix <= elem['x'] + w and elem['y'] <= iy <= elem['y'] + h:
                return (elem, 'body')
        return None

    def _delete_selected_bubble(self):
        """Delete the currently selected bubble."""
        if self.selected_bubble_id is None:
            return
        self.save_state()
        for elem in self.bubble_elements:
            if elem['id'] == self.selected_bubble_id:
                for cid in elem.get('canvas_ids', {}).values():
                    try:
                        self.canvas.delete(cid)
                    except Exception:
                        pass
                self.bubble_elements.remove(elem)
                break
        self.selected_bubble_id = None

    def _pick_custom_color(self):
        """Open the system color chooser for a custom hex color."""
        from tkinter import colorchooser
        result = colorchooser.askcolor(
            initialcolor=self.current_color,
            title="Choose Color",
        )
        if result and result[1]:
            self.set_color(result[1])

    def set_color(self, color):
        """Set the current drawing color with modern highlighting."""
        self.current_color = color

        # Update swatch highlights
        for btn in self.color_buttons:
            if btn.cget('bg') == color.lower():
                btn.config(highlightthickness=2, highlightbackground=Theme.PRIMARY)
            else:
                btn.config(highlightthickness=0)

        # Show chosen color on the "+" button
        self._custom_color_btn.config(bg=color)
    
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

        Returns (PhotoImage, width, height) for canvas display. The pixel
        data is produced by _render_step_pil; this method just wraps it for
        Tk. The save renderer calls _render_step_pil directly so saved
        files use the same pipeline (and therefore land in the same place)
        as the live preview.
        """
        tile = self._render_step_pil(elem, zoom=zoom)
        photo = ImageTk.PhotoImage(tile)
        return photo, tile.width, tile.height

    def _render_step_pil(self, elem, zoom=1.0):
        """Render a step element to a PIL RGBA Image, optionally scaled by `zoom`.

        At ``zoom`` = 1.0 the returned tile matches the element's
        image-space size. Larger/smaller zooms produce a correspondingly
        larger/smaller tile so the step lines up with the zoomed canvas
        background. The 4× supersampling is still performed in image
        space, then the final downsample targets the zoomed size, which
        keeps edges crisp at arbitrary zoom levels.
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
            new_ss_w = ss_w
            new_ss_h = ss_h
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
        if shape == 'teardrop':
            # Anchor the digit at the centroid of the bulb half-disk (model
            # (50 - 4r/3π, 50)). Using the arc center (50, 50) lands the
            # digit at the diameter — the boundary with the tail — so it
            # looks off-center; the tile bbox center lands it on the tail
            # at certain rotations. Track this anchor through the same
            # rotate-with-expand transform, then scale to tile coords.
            bulb_x_ss = mx + (50 - 4 * 40 / (3 * math.pi)) * ss_scale
            bulb_y_ss = my + 50 * ss_scale
            if rotation and rotation % 360 != 0:
                r = math.radians(rotation)
                cos_r = math.cos(r)
                sin_r = math.sin(r)
                crx, cry = ss_w / 2, ss_h / 2
                def _rot(px, py):
                    dx = px - crx
                    dy = py - cry
                    return crx + dx * cos_r - dy * sin_r, cry + dx * sin_r + dy * cos_r
                _corners = [(0, 0), (ss_w, 0), (ss_w, ss_h), (0, ss_h)]
                _rotated = [_rot(p[0], p[1]) for p in _corners]
                _min_x = min(p[0] for p in _rotated)
                _min_y = min(p[1] for p in _rotated)
                _bx, _by = _rot(bulb_x_ss, bulb_y_ss)
                bulb_after_x = _bx - _min_x
                bulb_after_y = _by - _min_y
            else:
                bulb_after_x = bulb_x_ss
                bulb_after_y = bulb_y_ss
            tcx = bulb_after_x * tile.width / new_ss_w
            tcy = bulb_after_y * tile.height / new_ss_h
        else:
            tcx = tile.width / 2
            tcy = tile.height / 2
        draw.text((tcx, tcy), str(step_num), fill=text_color, font=font, anchor="mm")

        return tile

    def _teardrop_anchor_in_tile(self, step_size, rotation, model_x, model_y):
        """Return where a teardrop model-space point (model_x, model_y) lands in
        the final downsampled (zoom=1) tile coords, accounting for rotation.

        Polygon model space spans x[10,135] y[10,90]: tail tip is (135, 50),
        arc center (bulb diameter) is (50, 50), bulb half-disk centroid is
        (50 - 4*40/(3*pi), 50).
        """
        pad = 10
        SS = 4
        rect_w = step_size * 1.4
        rect_h = step_size
        sw = int(rect_w) + pad * 2
        sh = int(rect_h) + pad * 2
        ss_w = sw * SS
        ss_h = sh * SS
        ss_scale = step_size * SS / 100.0
        mx = pad * SS
        my = pad * SS

        p_x_ss = mx + model_x * ss_scale
        p_y_ss = my + model_y * ss_scale

        if rotation and rotation % 360 != 0:
            r = math.radians(rotation)
            cos_r = math.cos(r)
            sin_r = math.sin(r)
            crx, cry = ss_w / 2, ss_h / 2

            def _rot(px, py):
                dx = px - crx
                dy = py - cry
                return crx + dx * cos_r - dy * sin_r, cry + dx * sin_r + dy * cos_r

            corners = [(0, 0), (ss_w, 0), (ss_w, ss_h), (0, ss_h)]
            rotated = [_rot(c[0], c[1]) for c in corners]
            min_x = min(p[0] for p in rotated)
            max_x = max(p[0] for p in rotated)
            min_y = min(p[1] for p in rotated)
            max_y = max(p[1] for p in rotated)
            new_ss_w = max_x - min_x
            new_ss_h = max_y - min_y
            _bx, _by = _rot(p_x_ss, p_y_ss)
            anchor_x = _bx - min_x
            anchor_y = _by - min_y
        else:
            new_ss_w = ss_w
            new_ss_h = ss_h
            anchor_x = p_x_ss
            anchor_y = p_y_ss

        return anchor_x * sw / new_ss_w, anchor_y * sh / new_ss_h

    def add_step_element(self, x, y):
        """Add a numbered step marker at the given position (canvas-only until save)."""
        # Snapshot the pre-mutation state so undo can remove this step and
        # restore the previous step_counter value.
        self.save_state()

        self.step_counter += 1
        step_num = self.step_counter

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

        # Place the tile so the click point coincides with the visual anchor
        # of the marker. For the teardrop the anchor is the tail tip — the
        # marker visually points at what the user clicked. For symmetric
        # shapes the click sits at the tile center.
        if self.step_shape == 'teardrop':
            tip_x, tip_y = self._teardrop_anchor_in_tile(
                self.step_size, self.step_rotation, 135, 50
            )
            x_pos = x - tip_x
            y_pos = y - tip_y
        else:
            half_size = self.step_size // 2
            x_pos = x - half_size
            y_pos = y - half_size

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

        elif self.current_tool == 'stamp':
            clicked_stamp = self._find_stamp_at(ix, iy)
            if clicked_stamp:
                self.selected_stamp_id = clicked_stamp['id']
                self.dragging_stamp = True
                self._drag_snapshot_taken = False
                self.drag_stamp_offset_x = ix - clicked_stamp['x']
                self.drag_stamp_offset_y = iy - clicked_stamp['y']
            else:
                self.drawing = False
                self.save_state()
                self._place_stamp(ix, iy)
            return

        elif self.current_tool == 'bubble':
            hit = self._bubble_hit_test(ix, iy)
            if hit:
                elem_b, zone = hit
                self.selected_bubble_id = elem_b['id']
                self._drag_snapshot_taken = False
                if zone == 'anchor':
                    self.dragging_bubble_anchor = True
                elif zone == 'resize':
                    self.dragging_bubble_resize = True
                else:  # 'body'
                    self.dragging_bubble = True
                    self.drag_bubble_offset_x = ix - elem_b['x']
                    self.drag_bubble_offset_y = iy - elem_b['y']
            else:
                self.drawing = False
                self._add_bubble(ix, iy)
            return

        elif self.current_tool == 'smart_move':
            if self.smart_move_phase == 'move' and self.smart_move_region:
                self.dragging_smart_move = True
                self._drag_snapshot_taken = False
                self.smart_move_drag_start_x = ix
                self.smart_move_drag_start_y = iy
                self.drawing = False
            # else: selection phase — let normal drawing behavior handle it
            return

        if self.current_tool in ('rectangle', 'circle', 'line', 'arrow', 'highlight'):
            clicked_shape = self._find_shape_at(ix, iy)
            if clicked_shape:
                self.selected_shape_id = clicked_shape['id']
                self.dragging_shape = True
                self._drag_snapshot_taken = False
                mid_x = (clicked_shape['x1'] + clicked_shape['x2']) / 2
                mid_y = (clicked_shape['y1'] + clicked_shape['y2']) / 2
                self.drag_shape_offset_x = ix - mid_x
                self.drag_shape_offset_y = iy - mid_y
                self.drawing = False
                return

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

        # Handle bubble dragging (body, anchor, or resize)
        if (self.dragging_bubble or self.dragging_bubble_anchor or self.dragging_bubble_resize) \
                and self.selected_bubble_id is not None:
            if not getattr(self, '_drag_snapshot_taken', False):
                self.save_state()
                self._drag_snapshot_taken = True
            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z
            for elem in self.bubble_elements:
                if elem['id'] == self.selected_bubble_id:
                    if self.dragging_bubble_anchor:
                        elem['anchor_x'] = ix
                        elem['anchor_y'] = iy
                    elif self.dragging_bubble_resize:
                        new_w = max(60, ix - elem['x'])
                        new_h = max(24, iy - elem['y'])
                        elem['width'] = new_w
                        elem['height'] = new_h
                    else:
                        elem['x'] = ix - self.drag_bubble_offset_x
                        elem['y'] = iy - self.drag_bubble_offset_y
                    self._render_bubble_canvas(elem)
                    break
            return

        # Handle stamp dragging
        if self.dragging_stamp and self.selected_stamp_id is not None:
            if not getattr(self, '_drag_snapshot_taken', False):
                self.save_state()
                self._drag_snapshot_taken = True
            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z
            for elem in self.stamp_elements:
                if elem['id'] == self.selected_stamp_id:
                    new_x = ix - self.drag_stamp_offset_x
                    new_y = iy - self.drag_stamp_offset_y
                    elem['x'] = new_x
                    elem['y'] = new_y
                    self._render_stamp_canvas(elem)
                    break
            return

        # Handle shape dragging
        if self.dragging_shape and self.selected_shape_id is not None:
            if not getattr(self, '_drag_snapshot_taken', False):
                self.save_state()
                self._drag_snapshot_taken = True
            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z
            for elem in self.shape_elements:
                if elem['id'] == self.selected_shape_id:
                    mid_x = (elem['x1'] + elem['x2']) / 2
                    mid_y = (elem['y1'] + elem['y2']) / 2
                    new_mid_x = ix - self.drag_shape_offset_x
                    new_mid_y = iy - self.drag_shape_offset_y
                    dx = new_mid_x - mid_x
                    dy = new_mid_y - mid_y
                    elem['x1'] += dx
                    elem['y1'] += dy
                    elem['x2'] += dx
                    elem['y2'] += dy
                    self._render_shape_canvas(elem)
                    break
            return

        # Handle smart move dragging
        if self.dragging_smart_move:
            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z
            dx = ix - self.smart_move_drag_start_x
            dy = iy - self.smart_move_drag_start_y
            for cid in self.smart_move_preview_ids:
                try:
                    self.canvas.delete(cid)
                except:
                    pass
            self.smart_move_preview_ids.clear()
            r = self.smart_move_region
            nx1, ny1 = (r[0] + dx) * z, (r[1] + dy) * z
            nx2, ny2 = (r[2] + dx) * z, (r[3] + dy) * z
            self.smart_move_preview_ids.append(
                self.canvas.create_rectangle(nx1, ny1, nx2, ny2,
                                             outline='#00FF00', width=2, dash=(5, 5))
            )
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

        # Draw preview for smart_move selection
        if self.current_tool == 'smart_move' and self.smart_move_phase == 'select':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline='#00FF00',
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

        if self.dragging_bubble or self.dragging_bubble_anchor or self.dragging_bubble_resize:
            self.dragging_bubble = False
            self.dragging_bubble_anchor = False
            self.dragging_bubble_resize = False
            return

        if self.dragging_stamp:
            self.dragging_stamp = False
            return

        if self.dragging_shape:
            self.dragging_shape = False
            return

        # Handle smart move release
        if self.current_tool == 'smart_move':
            if self.dragging_smart_move:
                self.dragging_smart_move = False
                cx, cy = self.get_canvas_coords(event)
                z = self.zoom if self.zoom else 1.0
                ix, iy = cx / z, cy / z
                dx = ix - self.smart_move_drag_start_x
                dy = iy - self.smart_move_drag_start_y

                self.save_state()
                r = self.smart_move_region
                # Fill vacated area
                self._fill_vacated_region(int(r[0]), int(r[1]), int(r[2]), int(r[3]))
                # Paste at new position
                new_x = int(r[0] + dx)
                new_y = int(r[1] + dy)
                self.image.paste(self.smart_move_snapshot, (new_x, new_y))

                # Clean up
                for cid in self.smart_move_preview_ids:
                    try:
                        self.canvas.delete(cid)
                    except:
                        pass
                self.smart_move_preview_ids.clear()
                self.smart_move_phase = 'select'
                self.smart_move_region = None
                self.smart_move_snapshot = None
                self.refresh_display()
                return

            elif self.smart_move_phase == 'select' and self.drawing:
                # Region selection complete — enter move phase
                self.drawing = False
                x, y = self.get_canvas_coords(event)
                if self.current_shape:
                    self.canvas.delete(self.current_shape)
                    self.current_shape = None

                z = self.zoom if self.zoom else 1.0
                ix1 = min(self.start_x, x) / z
                iy1 = min(self.start_y, y) / z
                ix2 = max(self.start_x, x) / z
                iy2 = max(self.start_y, y) / z

                if ix2 - ix1 < 5 or iy2 - iy1 < 5:
                    return

                self.smart_move_region = (ix1, iy1, ix2, iy2)
                self.smart_move_snapshot = self.image.crop(
                    (int(ix1), int(iy1), int(ix2), int(iy2))
                ).copy()
                self.smart_move_phase = 'move'

                # Show dashed selection on canvas
                self.smart_move_preview_ids.append(
                    self.canvas.create_rectangle(
                        ix1 * z, iy1 * z, ix2 * z, iy2 * z,
                        outline='#00FF00', width=2, dash=(5, 5)
                    )
                )
                self.status_var.set("SMART MOVE: Drag selection to new position")
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

        # Arrow tool — deferred rendering as shape element
        if self.current_tool == 'arrow':
            z = self.zoom if self.zoom else 1.0
            ax1, ay1 = self.start_x / z, self.start_y / z
            ax2, ay2 = x / z, y / z
            length = math.hypot(ax2 - ax1, ay2 - ay1)
            if length < 5:
                return
            self.shape_counter += 1
            elem = {
                'id': self.shape_counter,
                'type': 'arrow',
                'x1': ax1, 'y1': ay1, 'x2': ax2, 'y2': ay2,
                'color': self.current_color,
                'stroke_width': self.stroke_width,
                'arrow_style': self.arrow_style,
                'arrow_heads': self.arrow_heads,
                'canvas_id': None,
            }
            self.shape_elements.append(elem)
            self._render_shape_canvas(elem)
            self.refresh_display()
            return

        # Convert canvas coords to image coords (divide by zoom).
        z = self.zoom if self.zoom else 1.0
        ix1, iy1 = x1 / z, y1 / z
        ix2, iy2 = x2 / z, y2 / z

        if self.current_tool == 'rectangle':
            self.shape_counter += 1
            elem = {
                'id': self.shape_counter,
                'type': 'rectangle',
                'x1': ix1, 'y1': iy1, 'x2': ix2, 'y2': iy2,
                'color': self.current_color,
                'stroke_width': self.stroke_width,
                'canvas_id': None,
            }
            self.shape_elements.append(elem)
            self._render_shape_canvas(elem)
        elif self.current_tool == 'line':
            lx1, ly1 = self.start_x / z, self.start_y / z
            lx2, ly2 = x / z, y / z
            self.shape_counter += 1
            elem = {
                'id': self.shape_counter,
                'type': 'line',
                'x1': lx1, 'y1': ly1, 'x2': lx2, 'y2': ly2,
                'color': self.current_color,
                'stroke_width': self.stroke_width,
                'canvas_id': None,
            }
            self.shape_elements.append(elem)
            self._render_shape_canvas(elem)
        elif self.current_tool == 'circle':
            self.shape_counter += 1
            elem = {
                'id': self.shape_counter,
                'type': 'circle',
                'x1': ix1, 'y1': iy1, 'x2': ix2, 'y2': iy2,
                'color': self.current_color,
                'stroke_width': self.stroke_width,
                'canvas_id': None,
            }
            self.shape_elements.append(elem)
            self._render_shape_canvas(elem)
        elif self.current_tool == 'crop':
            self.image = self.image.crop((int(ix1), int(iy1), int(ix2), int(iy2)))
            self.refresh_display()
            return
        elif self.current_tool == 'highlight':
            self.shape_counter += 1
            elem = {
                'id': self.shape_counter,
                'type': 'highlight',
                'x1': ix1, 'y1': iy1, 'x2': ix2, 'y2': iy2,
                'color': self.current_color,
                'stroke_width': 1,
                'canvas_id': None,
            }
            self.shape_elements.append(elem)
            self._render_shape_canvas(elem)
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

    def _fill_vacated_region(self, x1, y1, x2, y2):
        """Fill a vacated rectangle by sampling border pixels and blending inward."""
        img = self.image
        w, h = img.size
        border = min(16, (x2 - x1) // 2, (y2 - y1) // 2)
        if border < 1:
            border = 1

        for y in range(max(0, y1), min(h, y2)):
            for x in range(max(0, x1), min(w, x2)):
                dl = x - x1
                dr = x2 - 1 - x
                dt = y - y1
                db = y2 - 1 - y

                samples = []
                weights = []

                if dl < border and x1 > 0:
                    src_x = max(0, x1 - 1)
                    w_val = 1.0 - (dl / border)
                    samples.append(img.getpixel((src_x, min(y, h - 1))))
                    weights.append(w_val)

                if dr < border and x2 < w:
                    src_x = min(w - 1, x2)
                    w_val = 1.0 - (dr / border)
                    samples.append(img.getpixel((src_x, min(y, h - 1))))
                    weights.append(w_val)

                if dt < border and y1 > 0:
                    src_y = max(0, y1 - 1)
                    w_val = 1.0 - (dt / border)
                    samples.append(img.getpixel((min(x, w - 1), src_y)))
                    weights.append(w_val)

                if db < border and y2 < h:
                    src_y = min(h - 1, y2)
                    w_val = 1.0 - (db / border)
                    samples.append(img.getpixel((min(x, w - 1), src_y)))
                    weights.append(w_val)

                if samples and weights:
                    total_w = sum(weights)
                    r = sum(s[0] * wt for s, wt in zip(samples, weights)) / total_w
                    g = sum(s[1] * wt for s, wt in zip(samples, weights)) / total_w
                    b = sum(s[2] * wt for s, wt in zip(samples, weights)) / total_w
                    img.putpixel((x, y), (int(r), int(g), int(b)))

    def on_canvas_motion(self, event):
        """Handle mouse motion for hover cursor feedback."""
        if self.dragging_text or self.dragging_step or self.dragging_stamp or self.dragging_shape or self.drawing:
            return

        x, y = self.get_canvas_coords(event)
        z = self.zoom if self.zoom else 1.0
        ix, iy = x / z, y / z

        if self.current_tool == 'step':
            hovered = self.find_step_at_position(x, y)
            if hovered:
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="")
        elif self.current_tool == 'stamp':
            if self._find_stamp_at(ix, iy):
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="")
        elif self.current_tool in ('rectangle', 'circle', 'line', 'arrow', 'highlight'):
            if self._find_shape_at(ix, iy):
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

        # Check for bubble double-click
        if self.current_tool == 'bubble':
            clicked_bubble = self._find_bubble_at(x, y)
            if clicked_bubble:
                new_text = self.prompt_text(clicked_bubble['text'])
                if new_text and new_text != clicked_bubble['text']:
                    self.save_state()
                    clicked_bubble['text'] = new_text
                    self._render_bubble_canvas(clicked_bubble)
                return

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

        # Bubbles: re-render canvas items at the current zoom.
        for elem in self.bubble_elements:
            self._render_bubble_canvas(elem)

        # Stamps: re-render at the current zoom.
        for elem in self.stamp_elements:
            self._render_stamp_canvas(elem)

        # Shapes: re-render at the current zoom.
        for elem in self.shape_elements:
            self._render_shape_canvas(elem)

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
        """Compose self.image plus all deferred annotation elements into a
        fresh PIL.Image and return it. Does NOT mutate self.image — every
        call starts from a clean copy of the current pristine canvas, so
        repeated invocations are idempotent and dragged elements no longer
        leave ghost copies at their previous positions."""
        self.deselect_all()
        out = self.image.copy()

        # Render shape elements first
        draw = ImageDraw.Draw(out)
        for elem in self.shape_elements:
            t = elem['type']
            if t == 'rectangle':
                draw.rectangle([elem['x1'], elem['y1'], elem['x2'], elem['y2']],
                               outline=elem['color'], width=elem['stroke_width'])
            elif t == 'circle':
                draw.ellipse([elem['x1'], elem['y1'], elem['x2'], elem['y2']],
                             outline=elem['color'], width=elem['stroke_width'])
            elif t == 'line':
                draw.line([(elem['x1'], elem['y1']), (elem['x2'], elem['y2'])],
                          fill=elem['color'], width=elem['stroke_width'])
            elif t == 'arrow':
                self._draw_arrow_on_image(draw, elem['x1'], elem['y1'], elem['x2'], elem['y2'],
                                          elem['color'], elem['stroke_width'],
                                          elem.get('arrow_style', 'filled'), elem.get('arrow_heads', 'single'))
            elif t == 'highlight':
                hx1, hy1 = int(min(elem['x1'], elem['x2'])), int(min(elem['y1'], elem['y2']))
                hx2, hy2 = int(max(elem['x1'], elem['x2'])), int(max(elem['y1'], elem['y2']))
                if hx2 > hx1 and hy2 > hy1:
                    region = out.crop((hx1, hy1, hx2, hy2))
                    overlay = Image.new('RGBA', region.size, elem['color'])
                    overlay.putalpha(89)
                    if region.mode != 'RGBA':
                        region = region.convert('RGBA')
                    region = Image.alpha_composite(region, overlay)
                    out.paste(region.convert('RGB'), (hx1, hy1))
                    draw = ImageDraw.Draw(out)

        # Render stamp elements
        for elem in self.stamp_elements:
            tile = elem['tile']
            paste_x = int(elem['x'] - elem['size'] // 2)
            paste_y = int(elem['y'] - elem['size'] // 2)
            if out.mode != 'RGBA':
                out = out.convert('RGBA')
            base = out.copy()
            base.paste(tile, (paste_x, paste_y), tile)
            out = base.convert('RGB')
            draw = ImageDraw.Draw(out)

        # Render text elements
        draw = ImageDraw.Draw(out)
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

        # Render bubble elements
        for elem in self.bubble_elements:
            try:
                from PIL import ImageFont
                font = ImageFont.truetype("arial.ttf", elem['font_size'])
            except:
                font = ImageFont.load_default()

            # Compute bubble dimensions (respects explicit width/height)
            tw_b, th_b = self._bubble_dims(elem)
            bx_s = elem['x']
            by_s = elem['y']
            bcx = bx_s + tw_b / 2
            bcy = by_s + th_b / 2
            ax_b, ay_b = elem['anchor_x'], elem['anchor_y']

            # Tail triangle from bubble edge toward anchor
            dx_b = ax_b - bcx
            dy_b = ay_b - bcy
            tail_w_s = max(8, min(20, tw_b * 0.15))
            if abs(dx_b) * th_b > abs(dy_b) * tw_b:
                if dx_b > 0:
                    ty_s = max(by_s + tail_w_s, min(by_s + th_b - tail_w_s, ay_b))
                    tail_pts = [(bx_s + tw_b, ty_s - tail_w_s / 2), (ax_b, ay_b), (bx_s + tw_b, ty_s + tail_w_s / 2)]
                else:
                    ty_s = max(by_s + tail_w_s, min(by_s + th_b - tail_w_s, ay_b))
                    tail_pts = [(bx_s, ty_s - tail_w_s / 2), (ax_b, ay_b), (bx_s, ty_s + tail_w_s / 2)]
            else:
                if dy_b > 0:
                    tx_s = max(bx_s + tail_w_s, min(bx_s + tw_b - tail_w_s, ax_b))
                    tail_pts = [(tx_s - tail_w_s / 2, by_s + th_b), (ax_b, ay_b), (tx_s + tail_w_s / 2, by_s + th_b)]
                else:
                    tx_s = max(bx_s + tail_w_s, min(bx_s + tw_b - tail_w_s, ax_b))
                    tail_pts = [(tx_s - tail_w_s / 2, by_s), (ax_b, ay_b), (tx_s + tail_w_s / 2, by_s)]

            # Parse hex color for RGBA overlay
            try:
                cr = int(elem['color'][1:3], 16)
                cg = int(elem['color'][3:5], 16)
                cb = int(elem['color'][5:7], 16)
            except:
                cr, cg, cb = 128, 128, 128
            fill_rgba = (cr, cg, cb, 210)

            bg_img = Image.new('RGBA', out.size, (0, 0, 0, 0))
            bg_draw = ImageDraw.Draw(bg_img)
            # Tail triangle
            bg_draw.polygon(tail_pts, fill=fill_rgba)
            # Rounded rectangle body
            bg_draw.rounded_rectangle(
                [bx_s, by_s, bx_s + tw_b, by_s + th_b],
                radius=8, fill=fill_rgba,
            )
            bg_draw.text((elem['x'] + 10, elem['y'] + 8), elem['text'], fill='white', font=font)

            if out.mode != 'RGBA':
                out = out.convert('RGBA')
            out = Image.alpha_composite(out, bg_img)
            out = out.convert('RGB')
            draw = ImageDraw.Draw(out)  # Refresh draw context after mode change

        # Render step elements with supersampled quality
        if not self.step_elements:
            return out

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

        img_w, img_h = out.size

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

            # Teardrops go through the live-preview pipeline so the saved
            # file's tail tip lands at the same canvas pixel the user sees in
            # the editor. The earlier save-only renderer used different pad
            # and rotation-center conventions, which shifted the saved tail
            # tip ~10 px up-left of the click for unrotated teardrops and
            # produced a larger offset at non-zero rotations.
            if shape == 'teardrop':
                tile = self._render_step_pil(elem, zoom=1.0)
                base = out.convert('RGBA')
                base.alpha_composite(
                    tile,
                    dest=(int(round(x_pos)), int(round(y_pos))),
                )
                out = base.convert('RGB')
                continue

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
                # Unreachable — teardrops are handled at the top of the loop
                # via the live-preview pipeline. Kept only so the elif chain
                # is exhaustive.
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
                new_ss_w = ss_size[0]
                new_ss_h = ss_size[1]
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
            if shape == 'teardrop':
                # Match _render_step_image: anchor digit at the centroid of
                # the bulb half-disk (model (50 - 4r/3π, 50)) — the visual
                # middle of the round portion, away from the tail boundary.
                # Use the shifted polygon origin (poly_mx, poly_my) so the
                # digit tracks the polygon's actual position in the tile.
                bulb_x_ss = poly_mx + (50 - 4 * 40 / (3 * math.pi)) * ss_scale
                bulb_y_ss = poly_my + 50 * ss_scale
                if rotation and rotation % 360 != 0:
                    r = math.radians(rotation)
                    cos_r = math.cos(r)
                    sin_r = math.sin(r)
                    crx, cry = ss_w / 2, ss_h / 2
                    def _rot(px, py):
                        dx = px - crx
                        dy = py - cry
                        return crx + dx * cos_r - dy * sin_r, cry + dx * sin_r + dy * cos_r
                    _w, _h = ss_size
                    _corners = [(0, 0), (_w, 0), (_w, _h), (0, _h)]
                    _rotated = [_rot(p[0], p[1]) for p in _corners]
                    _min_x = min(p[0] for p in _rotated)
                    _min_y = min(p[1] for p in _rotated)
                    _bx, _by = _rot(bulb_x_ss, bulb_y_ss)
                    bulb_after_x = _bx - _min_x
                    bulb_after_y = _by - _min_y
                else:
                    bulb_after_x = bulb_x_ss
                    bulb_after_y = bulb_y_ss
                tcx = bulb_after_x * tile_w / new_ss_w
                tcy = bulb_after_y * tile_h / new_ss_h
            else:
                tcx = tile_w / 2
                tcy = tile_h / 2
            tile_draw.text((tcx, tcy), str(step_num), fill=text_color, font=font, anchor="mm")

            # Composite onto export image
            base = out.convert('RGBA')
            ox = left
            oy = top
            base.alpha_composite(tile, dest=(ox, oy))
            out = base.convert('RGB')

        return out

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
            'bubble_elements': [dict(e, canvas_ids={}) for e in self.bubble_elements],
            'bubble_counter': self.bubble_counter,
            'stamp_elements': [dict(e, canvas_id=None, photo=None, tile=e['tile'].copy()) for e in self.stamp_elements],
            'stamp_counter': self.stamp_counter,
            'shape_elements': [dict(e, canvas_id=None) for e in self.shape_elements],
            'shape_counter': self.shape_counter,
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
        for elem in self.bubble_elements:
            for cid in elem.get('canvas_ids', {}).values():
                try:
                    self.canvas.delete(cid)
                except Exception:
                    pass
            elem['canvas_ids'] = {}
        for elem in self.stamp_elements:
            if elem.get('canvas_id'):
                try:
                    self.canvas.delete(elem['canvas_id'])
                except Exception:
                    pass
                elem['canvas_id'] = None
            elem.pop('photo', None)
        for elem in self.shape_elements:
            if elem.get('canvas_id'):
                try:
                    self.canvas.delete(elem['canvas_id'])
                except Exception:
                    pass
                elem['canvas_id'] = None
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

        # Restore bubbles
        for elem in self.bubble_elements:
            for cid in elem.get('canvas_ids', {}).values():
                try:
                    self.canvas.delete(cid)
                except Exception:
                    pass
        self.bubble_elements = [dict(e) for e in state.get('bubble_elements', [])]
        self.bubble_counter = state.get('bubble_counter', 0)
        self.selected_bubble_id = None
        for elem in self.bubble_elements:
            elem['canvas_ids'] = {}
            self._render_bubble_canvas(elem)

        # Restore stamps
        self.stamp_elements = [dict(e, canvas_id=None, photo=None, tile=e['tile'].copy()) for e in state.get('stamp_elements', [])]
        self.stamp_counter = state.get('stamp_counter', 0)
        self.selected_stamp_id = None

        # Restore shapes
        self.shape_elements = [dict(e, canvas_id=None) for e in state.get('shape_elements', [])]
        self.shape_counter = state.get('shape_counter', 0)
        self.selected_shape_id = None

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

            lib = self.library_path
            if lib and os.path.isfile(lib) and os.path.normcase(
                    os.path.dirname(os.path.abspath(lib))) == os.path.normcase(os.path.abspath(save_dir)):
                # The capture was already archived to the library, and the
                # library IS the storage folder — reuse that file instead of
                # writing a duplicate with a new timestamp.
                file_path = lib
                self.last_saved_path = lib
                print(f"Auto-save: reusing library file {lib}")
            else:
                # Compose annotations into a fresh export image
                export_image = self.render_annotations_to_image()

                # Generate filename with timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                format_ext = self.settings.get('image_format', 'png')
                filename = f"screensnap_{timestamp}.{format_ext}"
                file_path = os.path.join(save_dir, filename)

                # Save image
                export_image.save(file_path)
                self.last_saved_path = file_path
                print(f"Auto-saved: {file_path}")
            
            # Copy path to clipboard if enabled
            if self.settings.get('auto_copy_path', True):
                abs_path = os.path.abspath(file_path)
                if self._set_clipboard_text(abs_path):
                    self.status_var.set(f"✓ Auto-saved & path copied to clipboard")
                    print(f"Path copied to clipboard: {abs_path}")
                else:
                    self.status_var.set(f"✓ Auto-saved (clipboard busy — path not copied)")
                    print(f"Failed to copy to clipboard: clipboard busy after retries")
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
        # Compose annotations into a fresh export image
        export_image = self.render_annotations_to_image()

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
                export_image.save(file_path)
                self.last_saved_path = file_path
                # Also update the library copy if this image originated from library
                if self.library_path and os.path.exists(self.library_path):
                    export_image.save(self.library_path)
                self.status_var.set(f"Saved: {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")
    
    def _open_clipboard_with_retry(self, user32, attempts=10, delay_s=0.03):
        """OpenClipboard fails (returns 0) when another process briefly holds
        the clipboard — common with Win+V history, browsers, password
        managers, and clipboard tools. Retry a handful of times before
        giving up so users don't see silent no-ops on Save & Copy / Copy
        Image. Returns True on success."""
        import time
        for _ in range(attempts):
            if user32.OpenClipboard(None):
                return True
            time.sleep(delay_s)
        return False

    def _set_clipboard_text(self, text):
        """Place a string on the Windows clipboard as CF_UNICODETEXT, with
        OpenClipboard retries. Returns True on success, False otherwise.
        Replaces direct pyperclip.copy() calls which were silently failing
        under clipboard contention."""
        import ctypes
        import ctypes.wintypes as w

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        kernel32.GlobalAlloc.restype = w.HGLOBAL
        kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [w.HGLOBAL]
        kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
        user32.OpenClipboard.argtypes = [w.HWND]
        user32.SetClipboardData.restype = w.HANDLE
        user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]

        if not self._open_clipboard_with_retry(user32):
            return False
        try:
            user32.EmptyClipboard()
            buf = (text + '\0').encode('utf-16-le')
            hmem = kernel32.GlobalAlloc(0x0042, ctypes.c_size_t(len(buf)))
            ptr = kernel32.GlobalLock(hmem)
            ctypes.memmove(ptr, buf, len(buf))
            kernel32.GlobalUnlock(hmem)
            handle = user32.SetClipboardData(13, hmem)  # CF_UNICODETEXT = 13
            return bool(handle)
        finally:
            user32.CloseClipboard()

    def copy_image_to_clipboard(self):
        """Copy the current image to the Windows clipboard as a bitmap."""
        import io
        import ctypes
        import ctypes.wintypes as w
        export_image = self.render_annotations_to_image()
        try:
            img = export_image.convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='BMP')
            dib_data = buf.getvalue()[14:]  # skip BITMAPFILEHEADER

            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32

            # Set proper return types for 64-bit pointer safety
            kernel32.GlobalAlloc.restype = w.HGLOBAL
            kernel32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [w.HGLOBAL]
            kernel32.GlobalUnlock.argtypes = [w.HGLOBAL]
            user32.OpenClipboard.argtypes = [w.HWND]
            user32.SetClipboardData.restype = w.HANDLE
            user32.SetClipboardData.argtypes = [w.UINT, w.HANDLE]

            if not self._open_clipboard_with_retry(user32):
                self.status_var.set("Copy failed: clipboard busy — try again")
                messagebox.showerror(
                    "Clipboard Busy",
                    "Another app is holding the clipboard. Close any clipboard "
                    "manager / Win+V history pop-up and try again."
                )
                return
            try:
                user32.EmptyClipboard()
                hmem = kernel32.GlobalAlloc(0x0042, ctypes.c_size_t(len(dib_data)))
                ptr = kernel32.GlobalLock(hmem)
                ctypes.memmove(ptr, dib_data, len(dib_data))
                kernel32.GlobalUnlock(hmem)
                handle = user32.SetClipboardData(8, hmem)  # CF_DIB = 8
            finally:
                user32.CloseClipboard()
            if not handle:
                self.status_var.set("Copy failed: SetClipboardData returned NULL")
                messagebox.showerror("Error", "Failed to set image on clipboard.")
                return
            self.status_var.set("Image copied to clipboard!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy image: {e}")

    def ocr_current_image(self):
        """Extract text from current image via Tesseract and show preview dialog."""
        # Compose annotations into a fresh export image, matching Copy Image / Save behavior.
        export_image = self.render_annotations_to_image()

        self.status_var.set("Running OCR...")
        self.root.config(cursor="watch")
        self.root.update()
        try:
            text = run_ocr(export_image, self.settings)
        except TesseractNotFoundError:
            self.root.config(cursor="")
            self.status_var.set("OCR failed: Tesseract not found")
            self._prompt_install_tesseract()
            return
        except Exception as e:
            self.root.config(cursor="")
            self.status_var.set(f"OCR failed: {e}")
            messagebox.showerror("OCR Error", f"Tesseract failed:\n{e}")
            return
        finally:
            self.root.config(cursor="")

        copied = False
        if text:
            copied = self._set_clipboard_text(text)
            self.status_var.set(f"OCR: extracted {len(text)} characters")
        else:
            self.status_var.set("OCR: no text detected")

        OCRResultDialog(self.root, text, copied=copied)

    def _prompt_install_tesseract(self):
        """Show an error dialog with install link and Browse fallback."""
        INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
        answer = messagebox.askyesno(
            "Tesseract Not Installed",
            "Tesseract is required for OCR but was not found on this machine.\n\n"
            f"Install it from:\n{INSTALL_URL}\n\n"
            "Would you like to browse for an existing tesseract.exe now?"
        )
        if not answer:
            try:
                os.startfile(INSTALL_URL)
            except Exception:
                pass
            return

        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")],
        )
        if path and os.path.isfile(path):
            self.settings['tesseract_path'] = path
            SettingsManager.save(self.settings)
            # Retry
            self.ocr_current_image()

    def save_and_copy(self):
        """Save the image and copy path to clipboard."""
        # Compose annotations into a fresh export image
        export_image = self.render_annotations_to_image()

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
                export_image.save(file_path)
                self.last_saved_path = file_path

                # Copy absolute path to clipboard via retry-aware helper —
                # pyperclip silently no-ops when the clipboard is briefly
                # held by another process (Win+V, browsers, etc.).
                abs_path = os.path.abspath(file_path)
                if self._set_clipboard_text(abs_path):
                    self.status_var.set(f"Saved & copied to clipboard: {abs_path}")
                else:
                    self.status_var.set(f"Saved (clipboard busy): {abs_path}")
                    messagebox.showwarning(
                        "Clipboard Busy",
                        f"File was saved to:\n{abs_path}\n\n"
                        "But another app is holding the clipboard, so the path "
                        "could not be copied. Close any clipboard manager / "
                        "Win+V history pop-up and try Save & Copy again."
                    )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")

    def share_to_imgbb(self):
        """Upload image to ImgBB and copy link to clipboard."""
        # Compose annotations into a fresh export image
        export_image = self.render_annotations_to_image()

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
            result = upload_to_imgbb(export_image, api_key, auto_delete_seconds=86400)

            if 'error' in result:
                self.status_var.set(f"ImgBB upload failed: {result['error']}")
                messagebox.showerror("Upload Failed", result['error'])
            else:
                url = result['url']
                copied = self._set_clipboard_text(url)
                if copied:
                    self.status_var.set(f"Uploaded to ImgBB — link copied to clipboard")
                    clip_line = "Link has been copied to clipboard."
                else:
                    self.status_var.set(f"Uploaded to ImgBB (clipboard busy — link not copied)")
                    clip_line = "Clipboard was busy — copy the link manually."
                messagebox.showinfo(
                    "Upload Successful",
                    f"Image uploaded to ImgBB!\n\n"
                    f"Link: {url}\n\n"
                    f"Auto-deletes in 24 hours.\n"
                    f"{clip_line}"
                )
        finally:
            self.root.config(cursor="")


class OCRResultDialog:
    """Modal dialog showing OCR extracted text with Copy / Save / Close."""

    def __init__(self, parent, text, copied=False):
        self.parent = parent
        self.text = text or ""

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Extracted Text")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.config(bg=Theme.BACKGROUND)

        # Center
        self.dialog.update_idletasks()
        w, h = 600, 500
        x = (self.dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (h // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        main = tk.Frame(self.dialog, bg=Theme.BACKGROUND, padx=20, pady=20)
        main.pack(fill='both', expand=True)

        # Status line
        if not self.text:
            status_text = "No text detected."
            status_color = Theme.ON_SURFACE_VARIANT
        elif copied:
            status_text = f"Copied {len(self.text)} characters to clipboard"
            status_color = Theme.SUCCESS
        else:
            status_text = f"{len(self.text)} characters"
            status_color = Theme.ON_SURFACE_VARIANT
        tk.Label(main, text=status_text, font=("Segoe UI Bold", 10),
                 fg=status_color, bg=Theme.BACKGROUND).pack(anchor='w', pady=(0, 10))

        # Text area (read-only)
        text_frame = tk.Frame(main, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        text_frame.pack(fill='both', expand=True)

        self.text_widget = tk.Text(
            text_frame, wrap='word', font=("Consolas", 10),
            bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE,
            insertbackground=Theme.PRIMARY, relief='flat', borderwidth=8,
        )
        self.text_widget.insert('1.0', self.text)
        self.text_widget.config(state='disabled')
        scrollbar = ttk.Scrollbar(text_frame, orient='vertical',
                                  command=self.text_widget.yview)
        self.text_widget.config(yscrollcommand=scrollbar.set)
        self.text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Buttons
        btn_f = tk.Frame(main, bg=Theme.BACKGROUND)
        btn_f.pack(fill='x', pady=(15, 0))

        ModernButton(btn_f, text="CLOSE", variant="secondary",
                     command=self.dialog.destroy, width=10).pack(side='right', padx=5)

        if self.text:
            ModernButton(btn_f, text="💾 SAVE AS .TXT", variant="secondary",
                         command=self.save_to_file, width=16).pack(side='right', padx=5)
            ModernButton(btn_f, text="📋 COPY", variant="primary",
                         command=self.copy_to_clipboard, width=10).pack(side='right', padx=5)

        self.dialog.wait_window()

    def copy_to_clipboard(self):
        try:
            pyperclip.copy(self.text)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {e}")

    def save_to_file(self):
        path = filedialog.asksaveasfilename(
            title="Save Extracted Text",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.text)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")


class ThumbnailCache:
    """On-disk cache of library thumbnails, keyed by path + mtime + size.

    Decoding a multi-monitor PNG takes ~100ms, so a big library would be slow
    to browse without this. Entries are invalidated automatically when a file
    changes (the key includes mtime and size).
    """

    SIZE = (200, 125)
    _dir = None

    @classmethod
    def _cache_dir(cls):
        if cls._dir is None:
            base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
            cls._dir = Path(base) / 'ScreenSnap' / 'thumbs'
            try:
                cls._dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        return cls._dir

    @classmethod
    def _cache_file(cls, path):
        import hashlib
        st = os.stat(path)
        ident = f"{os.path.normcase(os.path.abspath(path))}|{st.st_mtime_ns}|{st.st_size}"
        return cls._cache_dir() / (hashlib.sha1(ident.encode('utf-8')).hexdigest() + '.jpg')

    @classmethod
    def get(cls, path):
        """Thumbnail of an image file as an RGB PIL image fitting within SIZE.

        Safe to call from a worker thread.
        """
        try:
            cache_file = cls._cache_file(path)
        except OSError:
            cache_file = None
        if cache_file is not None and cache_file.is_file():
            try:
                with Image.open(cache_file) as cached:
                    return cached.convert('RGB')
            except Exception:
                pass  # corrupt cache entry — rebuild below
        with Image.open(path) as im:
            im.draft('RGB', (cls.SIZE[0] * 2, cls.SIZE[1] * 2))  # cheap JPEG downscale; no-op otherwise
            thumb = im.convert('RGB')
        thumb.thumbnail(cls.SIZE, Image.LANCZOS)
        if cache_file is not None:
            try:
                thumb.save(cache_file, 'JPEG', quality=85)
            except Exception:
                pass
        return thumb

    @classmethod
    def forget(cls, path):
        """Drop the cached thumbnail for a file (call before deleting it)."""
        try:
            cls._cache_file(path).unlink()
        except Exception:
            pass


class LibraryBrowser:
    """Browser window for viewing and managing library screenshots with Midnight Architect styling.

    Shows the library as a thumbnail grid (default) or a grouped list. With
    pick_only=True (used from inside the editor) opening an item just records
    it in `selected_path` and closes, leaving the caller to load the image.
    """

    TILE_W = 216
    TILE_H = 160

    def __init__(self, parent, settings, pick_only=False):
        self.settings = settings
        self.pick_only = pick_only
        self.selected_path = None
        self._item_paths = {}   # Treeview item id -> full file path
        self._groups = []
        self._view = settings.get('library_view', 'thumbnails')
        if self._view not in ('thumbnails', 'list'):
            self._view = 'thumbnails'
        self._stale = {'thumbnails': True, 'list': True}  # view needs re-rendering
        # Date groups are lazy: only opened groups get rows/tiles/thumbnails, so
        # a library with thousands of screenshots opens as fast as an empty one.
        self._expanded = set()    # iids of opened date groups (shared by both views)
        self._shown = {}          # group iid -> tiles the grid shows (paging)
        self._lazy = {}           # list view: group iid -> closed group still to fill in
        self._loaded_once = False
        # Thumbnail grid state
        self._tiles = {}          # path -> tile frame
        self._tile_order = []     # paths in display order (arrow-key navigation)
        self._tile_groups = []    # [[tile, ...]] one list per date group
        self._thumb_selected = None
        self._thumb_cache = {}    # (path, mtime_ns) -> PhotoImage (also keeps refs alive)
        self._thumb_gen = 0       # bumped on reload/close so stale worker results are dropped
        self._thumb_queue = queue.SimpleQueue()
        self._cols = 1

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("ScreenSnap Library")
        self.dialog.resizable(True, True)
        self.dialog.minsize(640, 480)
        # From the launcher the root is withdrawn, so the dialog must NOT be
        # transient/grabbed: a transient of a withdrawn master is never mapped
        # on Windows (the window silently fails to appear) while grab_set on
        # the unviewable window raises TclError. From the editor the parent is
        # visible, so there it can be a proper modal.
        self.dialog.config(bg=Theme.BACKGROUND)
        if pick_only:
            try:
                self.dialog.transient(parent)
            except tk.TclError:
                pass

        # Center dialog
        self.dialog.update_idletasks()
        w, h = 1040, 700
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
        tk.Label(btn_frame, text="Today is loaded — click a date to load its screenshots",
                 font=("Segoe UI", 8), fg=Theme.ON_SURFACE_VARIANT,
                 bg=Theme.BACKGROUND).pack(side='left', padx=20)

        view_frame = tk.Frame(btn_frame, bg=Theme.BACKGROUND)
        view_frame.pack(side='right')
        self.view_buttons = {}
        for key, text in (('thumbnails', "▦  THUMBNAILS"), ('list', "☰  LIST")):
            btn = ModernButton(view_frame, text=text, variant="secondary", font=("Segoe UI Bold", 8),
                               command=lambda k=key: self._set_view(k))
            btn.pack(side='left', padx=(6, 0))
            self.view_buttons[key] = btn

        # Content area (The "Sunken" Void) — files grouped by creation date
        self.content = tk.Frame(main_frame, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        self.content.pack(fill='both', expand=True)

        # List view
        self.list_container = tk.Frame(self.content, bg=Theme.SURFACE_LOW)

        style = ttk.Style(self.dialog)
        style.configure('Library.Treeview',
                        background=Theme.SURFACE_LOW,
                        fieldbackground=Theme.SURFACE_LOW,
                        foreground=Theme.ON_SURFACE,
                        font=("Consolas", 10),
                        rowheight=26,
                        borderwidth=0)
        style.map('Library.Treeview',
                  background=[('selected', Theme.SURFACE_BRIGHT)],
                  foreground=[('selected', Theme.PRIMARY)])

        self.tree = ttk.Treeview(self.list_container, show='tree', selectmode='browse',
                                 style='Library.Treeview')
        self.tree.tag_configure('date_header', foreground=Theme.PRIMARY,
                                font=("Segoe UI Bold", 9))
        self.tree.tag_configure('empty', foreground='gray')

        v_scroll = ttk.Scrollbar(self.list_container, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)

        self.tree.pack(side='left', fill='both', expand=True)
        v_scroll.pack(side='right', fill='y')

        # Double-click to open (on a date header it just toggles the group)
        self.tree.bind('<Double-Button-1>', self.open_selected)
        self.tree.bind('<Return>', self.open_selected)
        # Date groups fill in when opened (see _populate_tree)
        self.tree.bind('<<TreeviewOpen>>', self._on_tree_open)
        self.tree.bind('<<TreeviewClose>>', self._on_tree_close)

        # Thumbnail view
        self.grid_container = tk.Frame(self.content, bg=Theme.SURFACE_LOW)
        self.canvas = tk.Canvas(self.grid_container, bg=Theme.SURFACE_LOW,
                                highlightthickness=0, yscrollincrement=40)
        g_scroll = ttk.Scrollbar(self.grid_container, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=g_scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        g_scroll.pack(side='right', fill='y')
        self.grid_inner = tk.Frame(self.canvas, bg=Theme.SURFACE_LOW)
        self._inner_id = self.canvas.create_window((0, 0), window=self.grid_inner, anchor='nw')
        self.grid_inner.bind('<Configure>',
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', self._on_canvas_configure)

        # Keyboard / wheel for the thumbnail grid (the Treeview handles its own)
        self.dialog.bind('<MouseWheel>', self._on_wheel)
        self.dialog.bind('<Return>', lambda e: self._grid_key(self.open_selected))
        self.dialog.bind('<Delete>', lambda e: self._grid_key(self.delete_selected))
        for key, (dr, dc) in (('Left', (0, -1)), ('Right', (0, 1)), ('Up', (-1, 0)), ('Down', (1, 0))):
            self.dialog.bind(f'<{key}>', lambda e, dr=dr, dc=dc: self._grid_key(self._move_selection, dr, dc))
        self.dialog.bind('<Escape>', lambda e: self.dialog.destroy())
        self.dialog.bind('<Destroy>', self._on_destroy)

        # Bottom buttons
        bottom_frame = tk.Frame(main_frame, bg=Theme.BACKGROUND)
        bottom_frame.pack(fill='x', pady=(20, 0))

        open_text = "✏️  OPEN IN EDITOR" if not pick_only else "✏️  OPEN THIS IMAGE"
        ModernButton(bottom_frame, text=open_text, variant="primary",
                     command=self.open_selected, width=20).pack(side='left')

        ModernButton(bottom_frame, text="🗑 DELETE", variant="danger",
                     command=self.delete_selected, width=12).pack(side='right', padx=5)

        ModernButton(bottom_frame, text="CLOSE", variant="secondary",
                     command=self.dialog.destroy, width=12).pack(side='right', padx=5)

        self._style_view_buttons()
        self._show_view()

        # Load library files
        self.load_library()
        self.dialog.after(40, self._poll_thumbs)
        self.dialog.focus_set()
        if pick_only:
            try:
                self.dialog.grab_set()
            except tk.TclError:
                pass

        # Block until dialog closes
        self.dialog.wait_window()

    # ── View switching ─────────────────────────────────────────────

    def _style_view_buttons(self):
        for key, btn in self.view_buttons.items():
            active = key == self._view
            btn._bg = Theme.PRIMARY if active else Theme.SURFACE_BRIGHT
            btn._abg = Theme.PRIMARY_GLOW if active else Theme.OUTLINE
            fg = "#000000" if active else Theme.ON_SURFACE
            btn.config(bg=btn._bg, fg=fg, activebackground=btn._abg, activeforeground=fg)

    def _show_view(self):
        self.list_container.pack_forget()
        self.grid_container.pack_forget()
        (self.grid_container if self._view == 'thumbnails' else self.list_container).pack(
            fill='both', expand=True)

    def _set_view(self, view):
        if view == self._view:
            return
        selected = self._selected_path()
        self._view = view
        self.settings['library_view'] = view
        try:
            # Re-load from disk rather than saving self.settings: the editor may
            # hand us a partial dict and saving that would wipe other settings.
            saved = SettingsManager.load()
            saved['library_view'] = view
            SettingsManager.save(saved)
        except Exception as e:
            print(f"Failed to remember library view: {e}")
        self._style_view_buttons()
        self._show_view()
        if self._stale[view]:
            self._render(view)
        if selected:
            self._select_path(selected)

    # ── Loading ────────────────────────────────────────────────────

    PAGE = 60   # tiles the grid shows per date group until "show more" is clicked

    def _scan(self):
        """Library files grouped by creation date, newest group first.

        One directory pass: DirEntry.stat() is served from the listing on
        Windows, so this costs no extra disk access per file.
        """
        groups = {}
        try:
            with os.scandir(LibraryManager.ensure_library()) as entries:
                for entry in entries:
                    if os.path.splitext(entry.name)[1].lower() not in LibraryManager.IMAGE_EXTS:
                        continue
                    try:
                        if not entry.is_file():
                            continue
                        st = entry.stat()
                    except OSError:
                        continue
                    # st_ctime is birth time on Windows
                    created = datetime.datetime.fromtimestamp(getattr(st, 'st_ctime', st.st_mtime))
                    groups.setdefault(created.date(), []).append(
                        (created, entry.path, st.st_size, st.st_mtime_ns))
        except OSError as e:
            print(f"Failed to read library folder: {e}")

        today = datetime.date.today()
        days = sorted(groups, reverse=True)
        result = []
        for day in days:
            if day == today:
                label = "Today"
            elif day == today - datetime.timedelta(days=1):
                label = "Yesterday"
            else:
                label = day.strftime("%A, %B %d, %Y")
            result.append({
                'iid': f"day-{day.isoformat()}",
                'label': label,
                'entries': sorted(groups[day], key=lambda e: e[0], reverse=True),
                # Opened by default: today (or the newest day, so the browser
                # isn't blank when nothing was captured today).
                'open': (day == today) or (today not in groups and day == days[0]),
            })
        return result

    def load_library(self):
        """(Re)scan the library folder and render the visible view.

        Only opened date groups are rendered with content; the rest stay
        collapsed headers until the user opens them.
        """
        self._groups = self._scan()
        known = {g['iid'] for g in self._groups}
        if not self._loaded_once:
            self._expanded = {g['iid'] for g in self._groups if g['open']}
            self._loaded_once = True
        else:
            self._expanded &= known  # keep the user's choices across refreshes
        self._stale = {'thumbnails': True, 'list': True}
        self._render(self._view)

    def _render(self, view):
        self._stale[view] = False
        if view == 'list':
            self._populate_tree()
        else:
            self._populate_grid()

    # ── List view ──────────────────────────────────────────────────

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._item_paths = {}
        self._lazy = {}
        if not self._groups:
            self.tree.insert('', 'end', text="(Library is empty — take a screenshot!)",
                             tags=('empty',))
            return
        for group in self._groups:
            iid = group['iid']
            is_open = iid in self._expanded
            self.tree.insert('', 'end', iid=iid,
                             text=f"{group['label']}  ({len(group['entries'])})",
                             open=is_open, tags=('date_header',))
            if is_open:
                self._fill_tree_group(group)
            else:
                # A placeholder child gives the group its expander arrow; the
                # real rows are only inserted when the user opens it.
                self.tree.insert(iid, 'end', iid=f"{iid}-pending", text="…")
                self._lazy[iid] = group

    def _fill_tree_group(self, group):
        for created, path, size, _mtime in group['entries']:
            display = f"{os.path.basename(path)}  ({size / 1024:.0f} KB, {created.strftime('%H:%M')})"
            item = self.tree.insert(group['iid'], 'end', text=display)
            self._item_paths[item] = path

    def _on_tree_open(self, event):
        iid = self.tree.focus()
        group = self._lazy.pop(iid, None)
        if group is not None:
            self.tree.delete(f"{iid}-pending")
            self._fill_tree_group(group)
        if iid.startswith('day-'):
            self._expanded.add(iid)

    def _on_tree_close(self, event):
        self._expanded.discard(self.tree.focus())

    # ── Thumbnail view ─────────────────────────────────────────────

    def _populate_grid(self):
        for child in self.grid_inner.winfo_children():
            child.destroy()
        keep = self._thumb_selected
        self._tiles = {}
        self._tile_order = []
        self._tile_groups = []
        self._thumb_selected = None
        self._thumb_gen += 1
        gen = self._thumb_gen

        if not self._groups:
            tk.Label(self.grid_inner, text="(Library is empty — take a screenshot!)",
                     font=("Segoe UI", 10), fg='gray', bg=Theme.SURFACE_LOW).pack(padx=20, pady=20)
            return

        todo = []
        for group in self._groups:
            iid = group['iid']
            entries = group['entries']
            is_open = iid in self._expanded
            header = tk.Label(self.grid_inner,
                              text=f"{'▾' if is_open else '▸'}  {group['label']}  ({len(entries)})",
                              font=("Segoe UI Bold", 9), fg=Theme.PRIMARY,
                              bg=Theme.SURFACE_LOW, cursor='hand2')
            header.pack(anchor='w', padx=8, pady=(12, 2))
            header.bind('<Button-1>', lambda e, i=iid: self._toggle_group(i))
            if not is_open:
                continue  # collapsed: no tiles, no thumbnails

            shown = self._shown.setdefault(iid, self.PAGE)
            tiles_frame = tk.Frame(self.grid_inner, bg=Theme.SURFACE_LOW)
            tiles_frame.pack(anchor='w', fill='x')
            tiles = []
            for created, path, size, mtime in entries[:shown]:
                tile = self._make_tile(tiles_frame, created, path, size)
                tiles.append(tile)
                self._tiles[path] = tile
                self._tile_order.append(path)
                photo = self._thumb_cache.get((path, mtime))
                if photo is not None:
                    tile.thumb_label.config(image=photo, text='')
                else:
                    todo.append((path, mtime))
            self._tile_groups.append(tiles)

            remaining = len(entries) - shown
            if remaining > 0:
                more = tk.Label(self.grid_inner,
                                text=f"Show {min(self.PAGE, remaining)} more  ({remaining} not shown)",
                                font=("Segoe UI Bold", 9), fg=Theme.PRIMARY, bg=Theme.SURFACE_BRIGHT,
                                padx=14, pady=6, cursor='hand2')
                more.pack(anchor='w', padx=12, pady=(0, 8))
                more.bind('<Button-1>', lambda e, i=iid: self._show_more(i))

        self._reflow()
        if keep in self._tiles:
            self._select_tile(keep, reveal=False)
        if todo:
            threading.Thread(target=self._thumb_worker, args=(gen, todo), daemon=True).start()

    def _rerender_grid(self):
        """Rebuild the grid, keeping the scroll position."""
        pos = self.canvas.yview()[0]
        self._populate_grid()
        self.dialog.after_idle(lambda: self.canvas.yview_moveto(pos))

    def _toggle_group(self, iid):
        if iid in self._expanded:
            self._expanded.discard(iid)
        else:
            self._expanded.add(iid)
        self._rerender_grid()

    def _show_more(self, iid):
        self._shown[iid] = self._shown.get(iid, self.PAGE) + self.PAGE
        self._rerender_grid()

    def _make_tile(self, parent, created, path, size):
        tile = tk.Frame(parent, bg=Theme.SURFACE, width=self.TILE_W, height=self.TILE_H,
                        highlightthickness=2, highlightbackground=Theme.SURFACE,
                        highlightcolor=Theme.SURFACE, cursor='hand2')
        tile.pack_propagate(False)
        box = tk.Frame(tile, bg=Theme.SURFACE_LOW, width=ThumbnailCache.SIZE[0],
                       height=ThumbnailCache.SIZE[1])
        box.pack(pady=(6, 4))
        box.pack_propagate(False)
        tile.thumb_label = tk.Label(box, text="…", fg=Theme.ON_SURFACE_VARIANT,
                                    bg=Theme.SURFACE_LOW, font=("Segoe UI", 9))
        tile.thumb_label.pack(expand=True)
        caption = tk.Label(tile, text=f"{created.strftime('%H:%M:%S')}  ·  {size / 1024:.0f} KB",
                           font=("Segoe UI", 8), fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE)
        caption.pack()
        for widget in (tile, box, tile.thumb_label, caption):
            widget.bind('<Button-1>', lambda e, p=path: self._select_tile(p))
            widget.bind('<Double-Button-1>', lambda e, p=path: (self._select_tile(p), self.open_selected()))
        return tile

    # ── Thumbnail grid mechanics ───────────────────────────────────

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._inner_id, width=event.width)
        cols = max(1, (event.width - 12) // (self.TILE_W + 12))
        if cols != self._cols:
            self._cols = cols
            self._reflow()

    def _reflow(self):
        for tiles in self._tile_groups:
            for i, tile in enumerate(tiles):
                tile.grid(row=i // self._cols, column=i % self._cols, padx=6, pady=6)

    def _thumb_worker(self, gen, todo):
        """Build thumbnails off the Tk thread, newest first."""
        for path, mtime in todo:
            if gen != self._thumb_gen:
                return  # library was reloaded or the dialog closed
            try:
                img = ThumbnailCache.get(path)
            except Exception:
                img = None
            self._thumb_queue.put((gen, path, mtime, img))

    def _poll_thumbs(self):
        """Turn finished thumbnails into PhotoImages (must happen on the Tk thread)."""
        try:
            for _ in range(6):
                try:
                    gen, path, mtime, img = self._thumb_queue.get_nowait()
                except queue.Empty:
                    break
                if gen != self._thumb_gen:
                    continue
                tile = self._tiles.get(path)
                if tile is None:
                    continue
                if img is None:
                    tile.thumb_label.config(text="⚠ unreadable", image='')
                    continue
                photo = ImageTk.PhotoImage(img)
                self._thumb_cache[(path, mtime)] = photo
                tile.thumb_label.config(image=photo, text='')
        except Exception as e:
            print(f"Thumbnail update failed: {e}")
        try:
            self.dialog.after(40, self._poll_thumbs)
        except tk.TclError:
            pass  # dialog was destroyed

    def _on_destroy(self, event):
        if event.widget is self.dialog:
            self._thumb_gen += 1  # tells the worker to stop

    def _on_wheel(self, event):
        if self._view == 'thumbnails':
            self.canvas.yview_scroll(-3 if event.delta > 0 else 3, 'units')

    def _select_tile(self, path, reveal=True):
        old = self._tiles.get(self._thumb_selected)
        if old is not None:
            old.config(highlightbackground=Theme.SURFACE, highlightcolor=Theme.SURFACE)
        self._thumb_selected = path
        tile = self._tiles.get(path)
        if tile is not None:
            tile.config(highlightbackground=Theme.PRIMARY, highlightcolor=Theme.PRIMARY)
            if reveal:
                self._ensure_visible(tile)
        self.dialog.focus_set()

    def _ensure_visible(self, tile):
        self.dialog.update_idletasks()
        top = tile.winfo_rooty() - self.grid_inner.winfo_rooty()
        bottom = top + tile.winfo_height()
        view_top = self.canvas.canvasy(0)
        view_h = self.canvas.winfo_height()
        total = max(1, self.grid_inner.winfo_height())
        if top < view_top:
            self.canvas.yview_moveto(max(0, (top - 10) / total))
        elif bottom > view_top + view_h:
            self.canvas.yview_moveto(min(1, (bottom - view_h + 10) / total))

    def _grid_key(self, action, *args):
        """Run a key action only while the thumbnail view is showing."""
        if self._view == 'thumbnails':
            action(*args)

    def _move_selection(self, d_row, d_col):
        if not self._tile_order:
            return
        if self._thumb_selected not in self._tiles:
            self._select_tile(self._tile_order[0])
            return
        # Move within the flat display order; Up/Down jump one row of tiles.
        step = d_col + d_row * self._cols
        index = self._tile_order.index(self._thumb_selected) + step
        self._select_tile(self._tile_order[max(0, min(len(self._tile_order) - 1, index))])

    # ── Selection / actions ────────────────────────────────────────

    def _selected_path(self):
        """Full path of the selected file, or None (headers, empty row)."""
        if self._view == 'thumbnails':
            return self._thumb_selected if self._thumb_selected in self._tiles else None
        sel = self.tree.selection()
        if not sel:
            return None
        return self._item_paths.get(sel[0])

    def _select_path(self, path):
        """Select `path` in the active view if it is present."""
        if self._view == 'thumbnails':
            if path in self._tiles:
                self._select_tile(path)
            return
        for item, item_path in self._item_paths.items():
            if item_path == path:
                self.tree.selection_set(item)
                self.tree.see(item)
                return

    def open_selected(self, event=None):
        """Open the selected file in the annotation editor (or hand it back to the caller)."""
        file_path = self._selected_path()
        if not file_path:
            return  # date header — double-click toggles the group natively

        if self.pick_only:
            self.selected_path = file_path
            self.dialog.destroy()
            return

        try:
            image = Image.open(file_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            self.dialog.destroy()
            AnnotationEditor(image, self.settings, library_path=file_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image: {e}")

    def delete_selected(self, event=None):
        """Delete the selected file."""
        file_path = self._selected_path()
        if not file_path:
            return

        if messagebox.askyesno("Confirm Delete", f"Delete this screenshot?\n\n{os.path.basename(file_path)}"):
            scroll_pos = self.canvas.yview()[0]
            try:
                ThumbnailCache.forget(file_path)
                os.remove(file_path)
                self.load_library()
                if self._view == 'thumbnails':
                    self.dialog.after_idle(lambda: self.canvas.yview_moveto(scroll_pos))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete: {e}")

    def open_folder(self):
        """Open the library folder in Windows Explorer."""
        lib_dir = LibraryManager.ensure_library()
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


def _kill_previous_instances():
    """Kill any existing ScreenSnap GUI processes (not this one)."""
    my_pid = os.getpid()
    try:
        # Use tasklist + taskkill to find and kill other ScreenSnap processes
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq ScreenSnap.exe', '/FO', 'CSV', '/NH'],
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
    parser = argparse.ArgumentParser(
        description='ScreenSnap - Portable Screenshot & Annotation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  screensnap                  Open launcher window
  screensnap full             Capture full screen, open editor
  screensnap region           Pick a region, window or UI element, open editor
  screensnap display          Pick a single display, open editor
  screensnap full --save C:\\output.png   Headless full screen save
        """
    )
    
    parser.add_argument(
        'mode',
        nargs='?',
        choices=['full', 'region', 'display'],
        help='Capture mode: full, region, or display'
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
        # GUI mode — kill any previous instance, then start fresh
        _kill_previous_instances()
        launcher = LauncherWindow(mode=args.mode)
        launcher.run()


if __name__ == '__main__':
    main()
