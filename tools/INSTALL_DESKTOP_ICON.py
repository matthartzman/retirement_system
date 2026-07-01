#!/usr/bin/env python3
"""Install desktop launchers for Retirement System v10."""
from __future__ import annotations
import platform, stat, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / 'Desktop'
DESKTOP.mkdir(exist_ok=True)
PY = 'pythonw' if platform.system() == 'Windows' else 'python3'
ICON = ROOT / 'frontend' / 'assets' / 'retirement_planner.ico'
UI_SCRIPT = ROOT / 'tools' / 'launchers' / 'START_DESKTOP.py'
RESET_SCRIPT = ROOT / 'tools' / 'set_local_mode.py'

def write_bat(name: str, script: Path) -> Path:
    target = DESKTOP / f'{name}.bat'
    target.write_text(f'@echo off\ncd /d "{ROOT}"\n{PY} "{script}"\n', encoding='utf-8')
    return target

def psq(value: Path | str) -> str:
    return str(value).replace("'", "''")

def create_windows_shortcut(name: str, script: Path) -> Path | None:
    lnk = DESKTOP / f'{name}.lnk'
    ps = "\n".join([
        "$WshShell = New-Object -ComObject WScript.Shell",
        f"$Shortcut = $WshShell.CreateShortcut('{psq(lnk)}')",
        f"$Shortcut.TargetPath = '{PY}'",
        f"$Shortcut.Arguments = '\"{psq(script)}\"'",
        f"$Shortcut.WorkingDirectory = '{psq(ROOT)}'",
        "$Shortcut.WindowStyle = 1",
        f"$Shortcut.IconLocation = '{psq(ICON)}'",
        "$Shortcut.Save()",
    ])
    try:
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-Command',ps], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return lnk
    except Exception:
        return None

launchers = [
    ('Retirement Planner', UI_SCRIPT),
    ('Retirement Planner - Reset Local Mode', RESET_SCRIPT),
]
if platform.system() == 'Windows':
    for name, script in launchers:
        created = create_windows_shortcut(name, script) or write_bat(name, script)
        print(f'Created {created}')
elif platform.system() == 'Darwin':
    for name, script in launchers:
        target = DESKTOP / f'{name}.command'
        target.write_text(f'#!/bin/bash\ncd "{ROOT}"\n{PY} "{script}"\n', encoding='utf-8')
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f'Created {target}')
else:
    for name, script in launchers:
        target = DESKTOP / f'{name}.desktop'
        target.write_text(f'[Desktop Entry]\nType=Application\nName={name}\nComment=Start Retirement System\nExec={PY} "{script}"\nIcon={ROOT / "frontend" / "assets" / "retirement_planner.svg"}\nTerminal=true\nCategories=Office;Finance;\n', encoding='utf-8')
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f'Created {target}')
