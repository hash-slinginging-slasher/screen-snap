"""Regression test for the PrtScn double-window bug.

Verifies the cross-process coordination that makes the in-app hotkey and the
external tray monitor mutually exclusive:
  - pid_alive() is reliable on Windows (os.kill(pid,0) is not),
  - a live hotkey-owner marker is detected as active,
  - a stale (dead-PID) marker is treated as inactive,
  - screensnap.py and the monitor agree on the marker path,
  - a recycled PID belonging to a non-ScreenSnap process is NOT treated as a
    live owner (would silently mute PrtScn on both sides),
  - the monitor lockfile probe used by the launcher's auto-start is a real
    liveness check (the old os.kill(pid,0) probe spawned duplicate monitors).
"""
import os
import sys
import subprocess
import time
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ss = _load("screensnap", os.path.join(HERE, "screensnap.py"))
    mon = _load("mon", os.path.join(HERE, "screensnap-printscreen-monitor.py"))

    lock = ss.hotkey_owner_lockfile()
    # Start clean.
    if os.path.exists(lock):
        os.remove(lock)

    # 1. pid_alive: live vs dead.
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(1)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    time.sleep(0.5)
    assert ss.pid_alive(live.pid) is True, "live pid should be alive"
    assert ss.pid_alive(dead.pid) is False, "dead pid should not be alive"
    assert ss.pid_alive(999999) is False, "bogus pid should not be alive"

    # 2. No marker -> nobody owns the hotkey; monitor would act.
    assert ss.hotkey_owner_active() is False
    assert mon._hotkey_owner_active() is False

    # 3. Live owner marker -> both sides see an active owner; monitor defers.
    with open(lock, "w") as f:
        f.write(str(live.pid))
    assert ss.hotkey_owner_active() is True
    assert mon._hotkey_owner_active() is True, "monitor must see the app's marker (path agreement)"

    # 4. Stale marker (dead PID) -> treated as inactive; monitor acts.
    with open(lock, "w") as f:
        f.write(str(dead.pid))
    assert ss.hotkey_owner_active() is False
    assert mon._hotkey_owner_active() is False

    # 5. Path agreement is exact between the two files.
    assert ss.hotkey_owner_lockfile() == mon._hotkey_owner_lockfile()

    # 6. write/clear round trip only clears our own marker.
    ss._write_hotkey_owner()
    assert os.path.exists(lock)
    with open(lock) as f:
        assert f.read().strip() == str(os.getpid())
    # Not our PID -> clear is a no-op.
    with open(lock, "w") as f:
        f.write(str(live.pid))
    ss._clear_hotkey_owner()
    assert os.path.exists(lock), "must not clear a marker owned by another process"
    # Our PID -> clear removes it.
    ss._write_hotkey_owner()
    ss._clear_hotkey_owner()
    assert not os.path.exists(lock)

    # 7. PID-reuse guard: a live process that is NOT ScreenSnap/Python must not
    # count as a hotkey owner, or the monitor defers to a ghost and PrtScn dies.
    foreign = subprocess.Popen(
        ["cmd", "/c", "ping -n 30 127.0.0.1 > nul"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.5)
    try:
        assert ss.pid_alive(foreign.pid) is True, "foreign process should be alive"
        assert ss._pid_is_screensnap(live.pid) is True, "python pid should look like ours"
        assert ss._pid_is_screensnap(foreign.pid) is False, "cmd.exe pid must not look like ours"
        assert mon._pid_is_screensnap(foreign.pid) is False, "monitor must agree on identity check"
        with open(lock, "w") as f:
            f.write(str(foreign.pid))
        assert ss.hotkey_owner_active() is False, "live foreign PID must not own the hotkey"
        assert mon._hotkey_owner_active() is False, "monitor must not defer to a foreign PID"

        # 8. Monitor lockfile probe (launcher auto-start). Must be a real
        # liveness+identity check, not os.kill(pid, 0) — and both sides must
        # agree on the (global, temp-dir) lock path so source-run and
        # dist-run ScreenSnaps share one monitor.
        assert str(ss.monitor_lockfile()) == str(mon._monitor_lockfile())
        mlock = os.path.join(HERE, ".test-monitor.lock")
        if os.path.exists(mlock):
            os.remove(mlock)
        try:
            assert ss._monitor_lock_active(mlock) is False, "missing lock -> not running"
            with open(mlock, "w") as f:
                f.write(str(dead.pid))
            assert ss._monitor_lock_active(mlock) is False, "dead pid -> not running"
            with open(mlock, "w") as f:
                f.write(str(live.pid))
            assert ss._monitor_lock_active(mlock) is True, "live python pid -> running"
            with open(mlock, "w") as f:
                f.write(str(foreign.pid))
            assert ss._monitor_lock_active(mlock) is False, "recycled foreign pid -> not running"
        finally:
            if os.path.exists(mlock):
                os.remove(mlock)
    finally:
        foreign.kill()
        if os.path.exists(lock):
            os.remove(lock)

    live.kill()
    print("ALL PASSED")


if __name__ == "__main__":
    main()
