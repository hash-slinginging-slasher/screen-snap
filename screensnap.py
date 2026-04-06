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


def capture_all_screens():
    """Capture all monitors as a single image."""
    bbox = get_all_screens_bbox()
    if bbox:
        return ImageGrab.grab(bbox=bbox, all_screens=True)
    else:
        return ImageGrab.grab(all_screens=True)


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
        """Get the config directory path."""
        return cls._get_base_dir() / "config"

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
            'image_format': 'png'
        }

        # Ensure config directory exists
        config_dir = cls.CONFIG_DIR()
        config_dir.mkdir(exist_ok=True)

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

        return settings

    @classmethod
    def save(cls, settings):
        """Save settings to INI file."""
        # Ensure config directory exists
        config_dir = cls.CONFIG_DIR()
        config_dir.mkdir(exist_ok=True)

        config = configparser.ConfigParser()
        config['Settings'] = {
            'default_save_path': settings.get('default_save_path', ''),
            'auto_save': str(settings.get('auto_save', False)).lower(),
            'auto_copy_path': str(settings.get('auto_copy_path', True)).lower(),
            'image_format': settings.get('image_format', 'png')
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
    
    def open_settings(self):
        """Open settings dialog."""
        self.root.wait_window(SettingsDialog(self.root, self.settings))
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

    def execute_full_capture(self):
        """Execute full screen capture and open editor."""
        try:
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
                # Load image
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
        self.root.mainloop()


class SettingsDialog:
    """Settings dialog for configuring auto-save with Midnight Architect styling."""
    
    def __init__(self, parent, settings):
        self.settings = settings.copy()
        self.result = False
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("System Settings")
        self.dialog.geometry("500x520")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.config(bg=Theme.BACKGROUND)
        
        # Center dialog
        self.dialog.update_idletasks()
        w, h = 500, 520
        x = (self.dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (h // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")
        
        # Main container
        main_frame = tk.Frame(self.dialog, bg=Theme.BACKGROUND, padx=30, pady=30)
        main_frame.pack(fill='both', expand=True)
        
        # Header
        tk.Label(main_frame, text="SETTINGS", font=("Segoe UI Bold", 10), 
                 fg=Theme.PRIMARY, bg=Theme.BACKGROUND).pack(anchor='w', pady=(0, 25))
        
        # Sections
        def create_section(parent, title):
            f = tk.Frame(parent, bg=Theme.SURFACE, padx=20, pady=20)
            f.pack(fill='x', pady=(0, 20))
            tk.Label(f, text=title.upper(), font=("Segoe UI Bold", 8), 
                     fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(anchor='w', pady=(0, 15))
            return f

        # 1. Capture Section
        capture_f = create_section(main_frame, "Capture & Save")
        
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
        path_f = create_section(main_frame, "Storage Location")
        self.path_var = tk.StringVar(value=settings.get('default_save_path', ''))
        path_entry_f = tk.Frame(path_f, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        path_entry_f.pack(fill='x', pady=(0, 10))
        
        tk.Entry(path_entry_f, textvariable=self.path_var, font=Theme.FONT_LABEL,
                 bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE, insertbackground=Theme.PRIMARY,
                 relief='flat', borderwidth=8).pack(side='left', fill='x', expand=True)
        
        ModernButton(path_f, text="BROWSE FOLDER", variant="secondary", 
                     command=self.browse_path, font=("Segoe UI Bold", 8)).pack(anchor='e')

        # 3. Format Section
        format_f = create_section(main_frame, "Image Format")
        self.format_var = tk.StringVar(value=settings.get('image_format', 'png'))
        format_opts = tk.Frame(format_f, bg=Theme.SURFACE)
        format_opts.pack(anchor='w')
        
        for fmt in ['png', 'jpg', 'bmp']:
            tk.Radiobutton(format_opts, text=fmt.upper(), value=fmt, variable=self.format_var,
                           font=Theme.FONT_LABEL, bg=Theme.SURFACE, fg=Theme.ON_SURFACE,
                           selectcolor=Theme.BACKGROUND, activebackground=Theme.SURFACE,
                           indicatoron=True).pack(side='left', padx=(0, 20))

        # Bottom Buttons
        btn_f = tk.Frame(main_frame, bg=Theme.BACKGROUND)
        btn_f.pack(side='bottom', fill='x', pady=(10, 0))
        
        ModernButton(btn_f, text="CANCEL", variant="secondary", command=self.dialog.destroy, width=12).pack(side='right', padx=5)
        ModernButton(btn_f, text="✓ SAVE CHANGES", variant="primary", command=self.save_settings, width=18).pack(side='right', padx=5)
    
    def browse_path(self):
        """Browse for a folder."""
        folder = filedialog.askdirectory(title="Select Default Save Folder")
        if folder:
            self.path_var.set(folder)
    
    def save_settings(self):
        """Save settings and close dialog."""
        self.settings['auto_save'] = self.auto_save_var.get()
        self.settings['default_save_path'] = self.path_var.get()
        self.settings['auto_copy_path'] = self.auto_copy_var.get()
        self.settings['image_format'] = self.format_var.get()
        
        # Validate path if auto-save is enabled
        if self.settings['auto_save'] and not self.settings['default_save_path']:
            messagebox.showwarning(
                "Warning",
                "Please select a default folder when auto-save is enabled."
            )
            return
        
        # Save to file
        SettingsManager.save(self.settings)
        self.result = True
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
        self.step_size = 30
        self.step_font_size = 14
        self.selected_step_id = None
        self.dragging_step = False
        self.drag_step_offset_x = 0
        self.drag_step_offset_y = 0

        # Use the shared app root as a Toplevel
        master = _get_root()
        _clear_root(master)
        self.root = tk.Toplevel(master)
        self.root.title("ScreenSnap - Annotation Editor")
        self.root.geometry("1400x850")
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
        # Also commit on Enter / focus-out so typed values are picked up
        step_size_spin.bind('<Return>', lambda e: self.update_step_size())
        step_size_spin.bind('<FocusOut>', lambda e: self.update_step_size())

        ModernButton(self.step_props_frame, text="↺ RESET", variant="secondary",
                     command=self.reset_step_counter, font=("Segoe UI Bold", 8)).pack(side='left', padx=5)

        # Canvas frame (The "Sunken" Void)
        canvas_container = tk.Frame(main_frame, bg=Theme.BACKGROUND, padx=20, pady=20)
        canvas_container.pack(side='top', fill='both', expand=True)

        self.canvas_bg = tk.Frame(canvas_container, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        self.canvas_bg.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(self.canvas_bg, bg=Theme.SURFACE_LOW, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        # Grid pattern for canvas
        self.root.after(100, self.draw_canvas_grid)

        # Display image
        self.display_image = ImageTk.PhotoImage(self.image)
        self.canvas.create_image(0, 0, image=self.display_image, anchor='nw')
        self.canvas.config(scrollregion=self.canvas.bbox('all'))

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
        self.root.bind('<Control-z>', self.undo)
        self.root.bind('<Control-s>', self.save)
        self.root.bind('<Escape>', self.deselect_all)

        # Tools shortcuts
        for k, t in [('r','rectangle'), ('l','line'), ('c','circle'), ('x','crop'), ('t','text'), ('p','step')]:
            self.root.bind(f'<{k}>', lambda e, tool=t: self.set_tool(tool))
            self.root.bind(f'<{k.upper()}>', lambda e, tool=t: self.set_tool(tool))

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

        # Update button states (Capsule highlight)
        for t in ['rectangle', 'line', 'circle', 'crop', 'text', 'step']:
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
        elif tool == 'step':
            self.step_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
        else:
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.deselect_all()
    
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
        
        # Add to canvas
        canvas_id = self.canvas.create_text(
            x, y,
            text=text,
            fill=text_element['color'],
            font=(text_element['font_family'], text_element['font_size']),
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
        
        # Draw blinking cursor at the START of text
        cursor_x = text_elem['x']
        cursor_y1 = text_elem['y']
        cursor_y2 = text_elem['y'] + text_elem['height']
        
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
        """Deselect all text elements."""
        self.selected_text_id = None
        # Remove all selection cursors
        self.canvas.delete('selection')
        for elem in self.text_elements:
            if 'cursor_id' in elem:
                del elem['cursor_id']
    
    def delete_selected_text(self, event=None):
        """Delete the selected text element."""
        if self.selected_text_id is None:
            return
        
        # Find and remove from canvas
        for i, elem in enumerate(self.text_elements):
            if elem['id'] == self.selected_text_id:
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
                
                # Recreate on canvas
                elem['canvas_id'] = self.canvas.create_text(
                    elem['x'], elem['y'],
                    text=elem['text'],
                    fill=elem['color'],
                    font=(elem['font_family'], elem['font_size']),
                    anchor='nw'
                )
                
                # Update dimensions
                temp_img = Image.new('RGB', (1, 1))
                draw = ImageDraw.Draw(temp_img)
                bbox = draw.textbbox((0, 0), elem['text'], font=font)
                elem['width'] = bbox[2] - bbox[0]
                elem['height'] = bbox[3] - bbox[1]
                
                # Update cursor position
                self.canvas.delete('selection')
                cursor_x = elem['x']
                cursor_y1 = elem['y']
                cursor_y2 = elem['y'] + elem['height']
                
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

    def add_step_element(self, x, y):
        """Add a numbered step marker at the given position."""
        # Increment step counter
        self.step_counter += 1
        step_num = self.step_counter

        # Calculate position (center the step on the click)
        half_size = self.step_size // 2
        x_pos = x - half_size
        y_pos = y - half_size

        # Save state for undo
        self.history.append(self.image.copy())

        # Snagit-style soft black drop shadow params (image coords).
        shadow_offset_x = 2
        shadow_offset_y = 4
        shadow_blur_radius = 8
        shadow_alpha = 140

        # Marker box dimensions (in image coords)
        if self.step_shape == 'rounded_rect':
            rect_width = self.step_size * 1.5
            rect_height = self.step_size * 1.2
        elif self.step_shape == 'teardrop':
            rect_width = self.step_size * 1.4
            rect_height = self.step_size
        else:  # circle, square
            rect_width = self.step_size
            rect_height = self.step_size

        # Prepare fill colour (RGBA tuple)
        fill_color = self.current_color
        if isinstance(fill_color, str) and fill_color.startswith('#'):
            r = int(fill_color[1:3], 16)
            g = int(fill_color[3:5], 16)
            b = int(fill_color[5:7], 16)
            fill_color = (r, g, b, 255)

        # Pick a number colour with enough contrast against the marker fill.
        # ITU-R BT.601 perceived luminance — threshold 150/255 marks "light" colours
        # (yellows, light greens, white, etc.) where white text would wash out.
        fill_luma = 0.299 * fill_color[0] + 0.587 * fill_color[1] + 0.114 * fill_color[2]
        text_color = 'black' if fill_luma > 150 else 'white'

        # Teardrop polygon helper, parameterised so it can be reused for the
        # supersampled PIL render and the live tk-canvas preview at different
        # scales / origins.
        def get_poly_pts(origin_x, origin_y, scale, off_x=0, off_y=0):
            """Teardrop points in pixel coords, centred on a 100x100 normalized
            space. (50,50) maps to the centre of the circular head."""
            pts = []
            # 1. Top-right curve (top of circle → point) — extra samples for smoothness
            p0, p1, p2, p3 = (50, 10), (100, 10), (135, 50), (135, 50)
            for i in range(21):
                t = i / 20.0
                px = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                py = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            # 2. Bottom-right curve (point → bottom of circle)
            p0, p1, p2, p3 = (135, 50), (135, 50), (100, 90), (50, 90)
            for i in range(1, 21):
                t = i / 20.0
                px = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                py = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            # 3. Left semicircle back to start
            for i in range(1, 41):
                angle = math.pi/2 + (i / 40.0) * math.pi
                px = 50 + 40 * math.cos(angle)
                py = 50 + 40 * math.sin(angle)
                pts.append((origin_x + px * scale + off_x, origin_y + py * scale + off_y))
            return pts

        # ── Render shadow + shape on a 4× supersampled tile, then LANCZOS-downsample.
        # PIL's polygon/ellipse/rounded_rectangle have weak (or no) anti-aliasing
        # at small sizes; rendering at 4× and resampling gives clean smooth edges.
        SS = 4
        pad = 26  # slack for shadow blur (~3*sigma) + offset

        img_w, img_h = self.image.size
        left   = max(0, int(x_pos - pad))
        top    = max(0, int(y_pos - pad))
        right  = min(img_w, int(x_pos + rect_width + shadow_offset_x + pad) + 1)
        bottom = min(img_h, int(y_pos + rect_height + shadow_offset_y + pad) + 1)
        tile_w = right - left
        tile_h = bottom - top

        if tile_w > 0 and tile_h > 0:
            ss_size = (tile_w * SS, tile_h * SS)
            # Marker top-left in tile-local pixel coords (image space)
            mx_img = x_pos - left
            my_img = y_pos - top
            mx = mx_img * SS
            my = my_img * SS
            sox = shadow_offset_x * SS
            soy = shadow_offset_y * SS

            # Shadow layer (drawn at 4× then blurred at 4× radius for crisp falloff)
            shadow_layer = Image.new('RGBA', ss_size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_layer)

            shape_layer = Image.new('RGBA', ss_size, (0, 0, 0, 0))
            shape_draw = ImageDraw.Draw(shape_layer)

            ss_w = rect_width * SS
            ss_h = rect_height * SS
            shadow_rgba = (0, 0, 0, shadow_alpha)

            if self.step_shape == 'circle':
                shadow_draw.ellipse(
                    [mx + sox, my + soy, mx + ss_w + sox, my + ss_h + soy],
                    fill=shadow_rgba,
                )
                shape_draw.ellipse(
                    [mx, my, mx + ss_w, my + ss_h],
                    fill=fill_color,
                )
            elif self.step_shape == 'square':
                shadow_draw.rounded_rectangle(
                    [mx + sox, my + soy, mx + ss_w + sox, my + ss_h + soy],
                    radius=6 * SS,
                    fill=shadow_rgba,
                )
                shape_draw.rounded_rectangle(
                    [mx, my, mx + ss_w, my + ss_h],
                    radius=6 * SS,
                    fill=fill_color,
                )
            elif self.step_shape == 'rounded_rect':
                radius_ss = (rect_height // 2) * SS
                shadow_draw.rounded_rectangle(
                    [mx + sox, my + soy, mx + ss_w + sox, my + ss_h + soy],
                    radius=radius_ss,
                    fill=shadow_rgba,
                )
                shape_draw.rounded_rectangle(
                    [mx, my, mx + ss_w, my + ss_h],
                    radius=radius_ss,
                    fill=fill_color,
                )
            elif self.step_shape == 'teardrop':
                ss_scale = (self.step_size * SS) / 100.0
                shadow_pts = get_poly_pts(mx, my, ss_scale, sox, soy)
                shape_pts = get_poly_pts(mx, my, ss_scale)
                shadow_draw.polygon(shadow_pts, fill=shadow_rgba)
                shape_draw.polygon(shape_pts, fill=fill_color)

            # Blur shadow at 4× radius so the falloff matches the original look
            from PIL import ImageFilter
            shadow_layer = shadow_layer.filter(
                ImageFilter.GaussianBlur(radius=shadow_blur_radius * SS)
            )

            # Combine shadow + shape on the supersampled tile
            tile = Image.alpha_composite(shadow_layer, shape_layer)
            # Downsample to image resolution with high-quality resampling
            tile = tile.resize((tile_w, tile_h), Image.LANCZOS)

            # Composite tile onto main image
            base = self.image.convert('RGBA')
            base.alpha_composite(tile, dest=(left, top))
            self.image = base.convert('RGB')

        draw = ImageDraw.Draw(self.image)

        # Image-coord polygon points for the canvas preview path below
        s = self.step_size / 100.0

        # Draw number with bold font
        try:
            from PIL import ImageFont
            font = None
            bold_fonts = ["segoeuib.ttf", "arialbd.ttf", "Verdana_Bold.ttf"]
            for f in bold_fonts:
                try:
                    font = ImageFont.truetype(f, self.step_font_size)
                    break
                except: continue
            if not font:
                font = ImageFont.truetype("arial.ttf", self.step_font_size)
        except:
            font = ImageFont.load_default()

        # Compute the visual center the number should sit on.
        # For teardrop, the circular head is centred at (50,50) in the normalized
        # 140x100 space, which maps back to the original click point (x, y).
        # For other shapes, use the rect centre.
        if self.step_shape == 'teardrop':
            text_cx = x
            text_cy = y
        else:
            text_cx = x_pos + rect_width / 2
            text_cy = y_pos + rect_height / 2

        # anchor="mm" positions the glyph's geometric centre at (text_cx, text_cy),
        # which is what we want — using textbbox + manual offset undercounts the
        # font's ascent and pushes the digit toward the bottom of the marker.
        draw.text((text_cx, text_cy), str(step_num), fill=text_color, font=font, anchor="mm")

        # Create canvas elements (preview)
        shadow_id = None
        bg_id = None
        text_id = None
        
        # Canvas elements use simpler shapes for performance.
        # Tk canvas can't render a true blurred drop shadow, so we approximate
        # the Snagit look with a soft offset shadow disc and a borderless fill.
        if self.step_shape == 'circle':
            shadow_id = self.canvas.create_oval(
                x_pos + shadow_offset_x, y_pos + shadow_offset_y,
                x_pos + rect_width + shadow_offset_x, y_pos + rect_height + shadow_offset_y,
                fill='#000000', outline=''
            )
            bg_id = self.canvas.create_oval(
                x_pos, y_pos, x_pos + rect_width, y_pos + rect_height,
                fill=self.current_color, outline=''
            )
        elif self.step_shape == 'square' or self.step_shape == 'rounded_rect':
            shadow_id = self.canvas.create_rectangle(
                x_pos + shadow_offset_x, y_pos + shadow_offset_y,
                x_pos + rect_width + shadow_offset_x, y_pos + rect_height + shadow_offset_y,
                fill='#000000', outline=''
            )
            bg_id = self.canvas.create_rectangle(
                x_pos, y_pos, x_pos + rect_width, y_pos + rect_height,
                fill=self.current_color, outline=''
            )
        elif self.step_shape == 'teardrop':
            shadow_id = self.canvas.create_polygon(
                get_poly_pts(x_pos, y_pos, s, shadow_offset_x, shadow_offset_y),
                fill='#000000', outline=''
            )
            bg_id = self.canvas.create_polygon(
                get_poly_pts(x_pos, y_pos, s),
                fill=self.current_color, outline=''
            )

        text_id = self.canvas.create_text(
            text_cx,
            text_cy,
            text=str(step_num),
            fill=text_color,
            font=("Arial", self.step_font_size, "bold")
        )

        # Store step element
        step_elem = {
            'id': step_num,
            'number': step_num,
            'x': x_pos,
            'y': y_pos,
            'size': self.step_size,
            'width': rect_width,
            'height': rect_height,
            'shape': self.step_shape,
            'color': self.current_color,
            'shadow_id': shadow_id,
            'bg_id': bg_id,
            'text_id': text_id
        }
        self.step_elements.append(step_elem)

        self.status_var.set(f"Step {step_num} added")
        self.refresh_display()

    def update_step_shape(self):
        """Update step shape from dropdown."""
        self.step_shape = self.step_shape_var.get()
        self.status_var.set(f"Step shape: {self.step_shape}")

    def update_step_size(self):
        """Update step size from spinner. Scales font proportionally so the
        number stays balanced inside the marker at any size."""
        try:
            new_size = int(self.step_size_var.get())
        except (tk.TclError, ValueError):
            new_size = 30
        # Clamp to the spinbox range
        new_size = max(16, min(120, new_size))
        self.step_size = new_size
        # Match the original 30→14 ratio (~0.47) so the digit stays well-fit
        self.step_font_size = max(8, int(round(new_size * 0.47)))
        # Reflect any clamping back into the var
        if self.step_size_var.get() != new_size:
            self.step_size_var.set(new_size)
        self.status_var.set(f"Step size: {self.step_size}")

    def reset_step_counter(self):
        """Reset the step counter to 0."""
        self.step_counter = 0
        self.status_var.set("Step counter reset to 0")

    def delete_last_step(self):
        """Delete the last step element."""
        if not self.step_elements:
            self.status_var.set("No steps to delete")
            return

        # Remove last step
        last_step = self.step_elements.pop()
        
        # Remove from canvas
        if last_step['shadow_id']:
            self.canvas.delete(last_step['shadow_id'])
        if last_step['bg_id']:
            self.canvas.delete(last_step['bg_id'])
        if last_step['text_id']:
            self.canvas.delete(last_step['text_id'])

        # Decrement counter
        self.step_counter -= 1

        # Save state for undo
        self.history.append(self.image.copy())

        # Remove from image - need to redraw without this step
        # For simplicity, we'll just refresh
        self.refresh_display()
        self.status_var.set(f"Deleted step {last_step['number']}")

    def refresh_all_steps(self):
        """Refresh all step elements on canvas (used after undo/redo)."""
        # This would be called to rebuild step elements after undo
        # For now, steps are drawn directly on the image
        pass

    def get_canvas_coords(self, event):
        """Get canvas coordinates accounting for scroll."""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        return x, y
    
    def on_canvas_press(self, event):
        """Handle canvas mouse press."""
        if not self.current_tool:
            return

        x, y = self.get_canvas_coords(event)
        self.drawing = True
        self.start_x = x
        self.start_y = y

        # Handle text tool
        if self.current_tool == 'text':
            # Check if clicking on existing text
            clicked_text = self.find_text_at_position(x, y)
            if clicked_text:
                # Select and prepare to drag
                self.select_text_element(clicked_text['id'])
                self.dragging_text = True
                self.drag_offset_x = x - clicked_text['x']
                self.drag_offset_y = y - clicked_text['y']
            else:
                # Add new text
                self.drawing = False
                self.add_text_element(x, y)

        # Handle step tool
        elif self.current_tool == 'step':
            # Check if clicking on existing step to drag
            clicked_step = self.find_step_at_position(x, y)
            if clicked_step:
                # Select and prepare to drag
                self.selected_step_id = clicked_step['id']
                self.dragging_step = True
                self.drag_step_offset_x = x - clicked_step['x']
                self.drag_step_offset_y = y - clicked_step['y']
            else:
                # Add new step
                self.drawing = False
                self.add_step_element(x, y)
    
    def on_canvas_drag(self, event):
        """Handle canvas mouse drag."""
        # Handle text dragging
        if self.dragging_text and self.selected_text_id is not None:
            x, y = self.get_canvas_coords(event)

            # Find selected text
            for elem in self.text_elements:
                if elem['id'] == self.selected_text_id:
                    # Move text
                    new_x = x - self.drag_offset_x
                    new_y = y - self.drag_offset_y

                    # Update canvas position
                    if elem['canvas_id']:
                        self.canvas.coords(elem['canvas_id'], new_x, new_y)

                    # Update position
                    elem['x'] = new_x
                    elem['y'] = new_y

                    # Update cursor position
                    self.canvas.delete('selection')
                    cursor_x = new_x
                    cursor_y1 = new_y
                    cursor_y2 = new_y + elem['height']

                    elem['cursor_id'] = self.canvas.create_line(
                        cursor_x, cursor_y1, cursor_x, cursor_y2,
                        fill='#2196F3',
                        width=2,
                        tags='selection'
                    )
                    break
            return

        # Handle step dragging
        if self.dragging_step and self.selected_step_id is not None:
            x, y = self.get_canvas_coords(event)

            # Find selected step
            for elem in self.step_elements:
                if elem['id'] == self.selected_step_id:
                    # Move step
                    new_x = x - self.drag_step_offset_x
                    new_y = y - self.drag_step_offset_y

                    # Update canvas positions
                    shadow_offset_x = 2
                    shadow_offset_y = 3
                    
                    # Calculate dimensions based on shape
                    if elem['shape'] in ['rounded_rect']:
                        elem_width = elem['size'] * 1.5
                        elem_height = elem['size'] * 1.8
                    elif elem['shape'] in ['teardrop']:
                        elem_width = elem['size']
                        elem_height = elem['size'] + 12
                    else:
                        elem_width = elem['size']
                        elem_height = elem['size']
                    
                    if elem['shadow_id'] is not None:
                        self.canvas.coords(elem['shadow_id'], 
                                          new_x + shadow_offset_x, new_y + shadow_offset_y, 
                                          new_x + elem_width + shadow_offset_x, new_y + elem_height + shadow_offset_y)
                    if elem['bg_id'] is not None:
                        self.canvas.coords(elem['bg_id'], new_x, new_y, new_x + elem_width, new_y + elem_height)
                    if elem['text_id'] is not None:
                        center_x = new_x + elem_width // 2
                        center_y = new_y + elem_height // 2
                        self.canvas.coords(elem['text_id'], center_x, center_y)

                    # Update position
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
        
        # Save state for undo
        self.history.append(self.image.copy())
        
        # Draw shape on image
        draw = ImageDraw.Draw(self.image)
        
        if self.current_tool == 'rectangle':
            draw.rectangle(
                [x1, y1, x2, y2],
                outline=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'line':
            draw.line(
                [(x1, y1), (x2, y2)],
                fill=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'circle':
            draw.ellipse(
                [x1, y1, x2, y2],
                outline=self.current_color,
                width=self.stroke_width
            )
        elif self.current_tool == 'crop':
            # Crop the image
            self.image = self.image.crop((int(x1), int(y1), int(x2), int(y2)))
            self.refresh_display()
            return
        
        self.refresh_display()
    
    def on_canvas_double_click(self, event):
        """Handle double-click to edit text."""
        x, y = self.get_canvas_coords(event)
        
        # Find text at position
        clicked_text = self.find_text_at_position(x, y)
        if clicked_text:
            # Prompt for new text
            new_text = self.prompt_text(clicked_text['text'])
            if new_text and new_text != clicked_text['text']:
                # Update text
                clicked_text['text'] = new_text
                
                # Recreate on canvas
                if clicked_text['canvas_id']:
                    self.canvas.delete(clicked_text['canvas_id'])
                
                clicked_text['canvas_id'] = self.canvas.create_text(
                    clicked_text['x'], clicked_text['y'],
                    text=new_text,
                    fill=clicked_text['color'],
                    font=(clicked_text['font_family'], clicked_text['font_size']),
                    anchor='nw'
                )
                
                # Update dimensions
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
                
                # Update cursor position
                self.canvas.delete('selection')
                cursor_x = clicked_text['x']
                cursor_y1 = clicked_text['y']
                cursor_y2 = clicked_text['y'] + clicked_text['height']
                
                clicked_text['cursor_id'] = self.canvas.create_line(
                    cursor_x, cursor_y1, cursor_x, cursor_y2,
                    fill='#2196F3',
                    width=2,
                    tags='selection'
                )
                
                self.status_var.set(f"Text updated: '{new_text}'")
    
    def refresh_display(self):
        """Refresh the canvas display with current image."""
        self.display_image = ImageTk.PhotoImage(self.image)
        self.canvas.create_image(0, 0, image=self.display_image, anchor='nw')
        self.canvas.config(scrollregion=self.canvas.bbox('all'))
    
    def render_text_to_image(self):
        """Render all text elements to the image before saving."""
        # Deselect all text first to remove selection boxes
        self.deselect_all()
        
        # Create a copy to draw on
        draw = ImageDraw.Draw(self.image)
        
        for elem in self.text_elements:
            # Get font
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(f"{elem['font_family'].lower().replace(' ', '')}.ttf", elem['font_size'])
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", elem['font_size'])
                except:
                    font = ImageFont.load_default()
            
            # Draw text
            draw.text(
                (elem['x'], elem['y']),
                elem['text'],
                fill=elem['color'],
                font=font
            )
    
    def undo(self, event=None):
        """Undo the last action."""
        if not self.history:
            self.status_var.set("Nothing to undo")
            return
        
        self.image = self.history.pop()
        self.refresh_display()
        self.status_var.set(f"Undo ({len(self.history)} remaining)")
    
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
            self.render_text_to_image()
            
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
        self.render_text_to_image()

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
        self.render_text_to_image()
        
        # If we have a last saved path, use it
        if self.last_saved_path:
            file_path = self.last_saved_path
        else:
            # Otherwise ask for a path
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
                
                # Copy absolute path to clipboard
                abs_path = os.path.abspath(file_path)
                pyperclip.copy(abs_path)
                
                self.status_var.set(f"Saved & copied to clipboard: {abs_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")


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
