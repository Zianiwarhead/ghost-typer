"""Builds dist/GhostTyper.exe via PyInstaller (Windows).

Deliberately NO --uac-admin: an always-elevated binary pops a UAC prompt on
every launch and looks hostile to Defender. Standard user-level rights type
into every normal app; to reach an *elevated* window, run an elevated
terminal instead (elevation parity is a Windows rule, not a bug).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    if sys.platform != "win32":
        print("[-] Exe builds need Windows.")
        return 1
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[-] PyInstaller not installed. Run: pip install pyinstaller")
        return 1
    icon = os.path.join(ROOT, "assets", "icon.ico")
    args = [sys.executable, "-m", "PyInstaller", "--onefile", "--console",
            "--name=GhostTyper", "--clean", "main.py"]
    if os.path.exists(icon):
        args[4:4] = [f"--icon={icon}"]
    print("[*] Building:", " ".join(args[3:]))
    try:
        subprocess.run(args, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[-] Build failed: {e}")
        return 1
    print("\n[+] Done: dist\\GhostTyper.exe")
    print("    Note: stdlib-only server (http.server) needs no hidden imports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
