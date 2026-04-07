# ScreenSnap Print Screen Integration

## Set ScreenSnap as Default Print Screen Handler

ScreenSnap can now intercept the **Print Screen (PrtScn)** key on Windows 10/11. When you press Print Screen, ScreenSnap will launch with region capture mode.

---

## Method 1: Background Monitor (Recommended - Works on All Windows 10/11)

This method runs a lightweight background service that monitors the Print Screen key and launches ScreenSnap when pressed.

### Setup:

1. **Install and start the monitor:**
   ```cmd
   install-printscreen-monitor.bat
   ```

2. **A system tray icon will appear** in the notification area (bottom-right corner)

3. **Press Print Screen** - ScreenSnap will launch with region capture!

### Management:

- **Stop the monitor:** Run `stop-printscreen-monitor.bat`
- **Check status:** Right-click the system tray icon → "Show Status"
- **Quit:** Right-click the system tray icon → "Quit"

### Dependencies:
The monitor requires these Python packages (auto-installed on first run):
- `keyboard` - Global keyboard hook
- `pystray` - System tray icon
- `Pillow` - Icon rendering

---

## Method 2: Windows 11 Group Policy (Pro/Enterprise Only)

For Windows 11 Pro/Enterprise (Build 26300+), you can enable third-party Print Screen interception via Group Policy:

1. Press `Win + R`, type `gpedit.msc`, press Enter
2. Navigate to: **Computer Configuration → Administrative Templates → Windows Components → File Explorer**
3. Find **"Make Print Screen key yieldable"**
4. Set to **Enabled** or **Not Configured**
5. **Reboot** your computer

Then use **Method 1** to run the background monitor.

---

## Method 3: Manual Shortcut (No Background Service)

If you don't want a background service, you can create a manual shortcut:

1. Right-click on Desktop → **New → Shortcut**
2. Enter location: `D:\qwen\screenshot-easy\screensnap-exe.bat region`
3. Name it: "ScreenSnap Region Capture"
4. Right-click the shortcut → **Properties**
5. Click in **Shortcut key** field and press `Ctrl + Alt + P` (or any combination)
6. Click **OK**

Now press your custom shortcut to launch ScreenSnap.

---

## How It Works

The background monitor (`screensnap-printscreen-monitor.py`):
- Uses the `keyboard` library to register a **global keyboard hook**
- Listens for Print Screen key press events
- Launches `screensnap-exe.bat region` in a new console window
- Runs silently in the system tray
- Has a 0.5-second cooldown to prevent double-triggering
- Tracks capture count for the session

---

## Troubleshooting

### Monitor won't start
- Ensure Python 3.10+ is installed and in PATH
- Run `install-printscreen-monitor.bat` as a regular user (no admin needed)

### Print Screen not working
- Check if the monitor is running (look for tray icon)
- Right-click tray icon → "Show Status" to verify
- Ensure no other app is intercepting Print Screen (e.g., OneDrive, Snipping Tool)

### Double captures
- The monitor has a built-in 0.5s cooldown
- If you still get double captures, increase the sleep time in `screensnap-printscreen-monitor.py` line 68

### Uninstall
1. Run `stop-printscreen-monitor.bat`
2. Optionally uninstall dependencies:
   ```cmd
   pip uninstall keyboard pystray
   ```

---

## Files Added

| File | Purpose |
|---|---|
| `screensnap-printscreen-monitor.py` | Background service that monitors Print Screen key |
| `install-printscreen-monitor.bat` | Install and start the monitor |
| `stop-printscreen-monitor.bat` | Stop the monitor |
| `set-default-printscreen.bat` | ~~Legacy registry method (not used)~~ |
| `unregister-printscreen.bat` | ~~Legacy registry removal (not used)~~ |

---

## Notes

- The monitor runs as a standard user process (no admin rights required)
- It only intercepts Print Screen when the monitor is actively running
- Windows' built-in Snipping Tool may still activate on some Windows versions
- For complete replacement, disable Snipping Tool in Windows Settings
