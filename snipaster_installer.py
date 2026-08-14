#!/usr/bin/env python3
"""Shared installer for Snipaster's animated and plain entry points."""

from __future__ import annotations

import ast
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

Progress = Callable[[str], None]
SOURCE_DIR = Path(__file__).resolve().parent
MANAGED_XBINDKEYS_START = "# >>> Snipaster managed shortcut >>>"
MANAGED_XBINDKEYS_END = "# <<< Snipaster managed shortcut <<<"
GNOME_MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
GNOME_BINDING_BASE = (
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom"
)


class InstallError(RuntimeError):
    """Raised when the user-level installation cannot be completed safely."""


@dataclass(frozen=True)
class PackageSpec:
    package: str
    probe: tuple[str, ...]


@dataclass(frozen=True)
class InstallPaths:
    home: Path
    app_dir: Path
    bin_dir: Path
    launcher: Path
    compatibility_launcher: Path
    icon: Path
    applications_entry: Path
    desktop_entry: Path
    tray_autostart: Path


@dataclass(frozen=True)
class InstallationResult:
    paths: InstallPaths
    hotkey: str
    tray_started: bool


PACKAGE_SPECS = (
    PackageSpec(
        "python3-pyqt5",
        ("/usr/bin/python3", "-c", "from PyQt5 import QtCore, QtGui, QtWidgets"),
    ),
    PackageSpec("libqt5svg5", ("dpkg-query", "-W", "-f=${Status}", "libqt5svg5")),
    PackageSpec("qtwayland5", ("dpkg-query", "-W", "-f=${Status}", "qtwayland5")),
    PackageSpec("gnome-screenshot", ("sh", "-c", "command -v gnome-screenshot")),
    PackageSpec("scrot", ("sh", "-c", "command -v scrot")),
    PackageSpec("xbindkeys", ("sh", "-c", "command -v xbindkeys")),
    PackageSpec("libnotify-bin", ("sh", "-c", "command -v notify-send")),
    PackageSpec("xdg-utils", ("sh", "-c", "command -v xdg-open")),
)


def _run(
    command: Iterable[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _probe_succeeds(command: tuple[str, ...]) -> bool:
    try:
        result = _run(command, check=False, capture=True)
    except OSError:
        return False
    if result.returncode != 0:
        return False
    if command and command[0] == "dpkg-query":
        return "install ok installed" in result.stdout
    return True


def missing_packages() -> list[str]:
    """Return packages whose runtime probe currently fails."""

    return [spec.package for spec in PACKAGE_SPECS if not _probe_succeeds(spec.probe)]


def prepare_privileges() -> list[str]:
    """Cache sudo credentials before an animated installation starts."""

    if os.name == "nt":
        return []
    if os.geteuid() == 0:
        raise InstallError(
            "Run the installer as your normal desktop user, not with sudo. "
            "Snipaster requests sudo only for missing Ubuntu packages."
        )
    missing = missing_packages()
    if not missing:
        return []
    sudo = shutil.which("sudo")
    if not sudo:
        raise InstallError("sudo is required to install missing Ubuntu packages.")
    try:
        _run([sudo, "-v"])
    except subprocess.CalledProcessError as exc:
        raise InstallError("Administrator permission was not granted.") from exc
    return missing


def ensure_packages(progress: Progress) -> None:
    missing = missing_packages()
    if not missing:
        progress("System packages are already installed.")
        return

    sudo = shutil.which("sudo")
    if not sudo:
        raise InstallError(
            "Missing packages cannot be installed because sudo is unavailable: "
            + ", ".join(missing)
        )

    progress("Refreshing Ubuntu package metadata...")
    update = _run(
        [sudo, "apt-get", "update"], check=False, capture=True
    )
    if update.returncode != 0:
        details = "\n".join(update.stderr.strip().splitlines()[-8:])
        raise InstallError(
            "Ubuntu package metadata refresh failed."
            + (f"\n{details}" if details else "")
        )

    progress("Installing: " + ", ".join(missing))
    package_install = _run(
        [sudo, "apt-get", "install", "-y", *missing],
        check=False,
        capture=True,
    )
    if package_install.returncode != 0:
        details = "\n".join(package_install.stderr.strip().splitlines()[-8:])
        raise InstallError(
            "Ubuntu package installation failed."
            + (f"\n{details}" if details else "")
        )

    unresolved = missing_packages()
    if unresolved:
        raise InstallError(
            "These runtime requirements are still unavailable after apt completed: "
            + ", ".join(unresolved)
        )


def install_paths(home: Optional[Path] = None) -> InstallPaths:
    root = (home or Path.home()).expanduser().resolve()
    if os.name == "nt":
        app_dir = (
            root / "AppData" / "Local" / "Snipaster"
            if home is not None
            else Path(os.environ.get("LOCALAPPDATA", root / "AppData" / "Local"))
            / "Snipaster"
        )
        roaming = (
            root / "AppData" / "Roaming"
            if home is not None
            else Path(os.environ.get("APPDATA", root / "AppData" / "Roaming"))
        )
        programs = roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        desktop = resolve_desktop_dir(root)
        return InstallPaths(
            home=root,
            app_dir=app_dir,
            bin_dir=app_dir,
            launcher=app_dir / "snipaster.cmd",
            compatibility_launcher=app_dir / "snipaster_shot.cmd",
            icon=app_dir / "snipaster-icon.svg",
            applications_entry=programs / "Snipaster.cmd",
            desktop_entry=desktop / "Snipaster.cmd",
            tray_autostart=programs / "Startup" / "Snipaster Tray.cmd",
        )
    app_dir = root / ".local" / "share" / "snipaster"
    bin_dir = root / ".local" / "bin"
    applications = root / ".local" / "share" / "applications"
    icon = (
        root
        / ".local"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / "snipaster.svg"
    )
    desktop_dir = resolve_desktop_dir(root)
    return InstallPaths(
        home=root,
        app_dir=app_dir,
        bin_dir=bin_dir,
        launcher=bin_dir / "snipaster",
        compatibility_launcher=bin_dir / "snipaster_shot",
        icon=icon,
        applications_entry=applications / "snipaster.desktop",
        desktop_entry=desktop_dir / "Snipaster.desktop",
        tray_autostart=root / ".config" / "autostart" / "snipaster-tray.desktop",
    )


def resolve_desktop_dir(home: Path) -> Path:
    if os.name == "nt":
        one_drive = os.environ.get("OneDrive")
        if home == Path.home().expanduser().resolve() and one_drive:
            candidate = Path(one_drive) / "Desktop"
            if candidate.is_dir():
                return candidate
        return home / "Desktop"
    xdg_user_dir = shutil.which("xdg-user-dir")
    if xdg_user_dir and home == Path.home().expanduser().resolve():
        result = _run([xdg_user_dir, "DESKTOP"], check=False, capture=True)
        candidate = Path(result.stdout.strip()).expanduser()
        if result.returncode == 0 and candidate.is_absolute():
            return candidate
    return home / "Desktop"


def _desktop_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def desktop_exec(executable: Path, *arguments: str) -> str:
    return " ".join(_desktop_quote(part) for part in (str(executable), *arguments))


def make_application_entry(paths: InstallPaths) -> str:
    capture = desktop_exec(paths.launcher, "capture")
    annotate = desktop_exec(paths.launcher, "annotate")
    open_folder = desktop_exec(paths.launcher, "open-folder")
    return f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Snipaster
GenericName=Screenshot and annotation tool
Comment=Capture a region, draw, add text, crop, save, and copy
Exec={annotate}
TryExec={paths.launcher}
Icon={paths.icon}
Terminal=false
StartupNotify=true
Categories=Graphics;Utility;
Keywords=screenshot;capture;snip;annotation;draw;text;crop;
Actions=Capture;Annotate;OpenScreenshots;
X-GNOME-UsesNotifications=true

[Desktop Action Capture]
Name=Capture a screen region
Exec={capture}
Icon={paths.icon}

[Desktop Action Annotate]
Name=Capture and annotate
Exec={annotate}
Icon={paths.icon}

[Desktop Action OpenScreenshots]
Name=Open Screenshots
Exec={open_folder}
Icon=folder-pictures
"""


def make_tray_autostart_entry(paths: InstallPaths) -> str:
    return f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Snipaster Capture Icon
Comment=Keep one-click Snipaster capture available in the desktop tray
Exec={desktop_exec(paths.launcher, "tray")}
TryExec={paths.launcher}
Icon={paths.icon}
Terminal=false
NoDisplay=true
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-GNOME-UsesNotifications=true
"""


def _write_text(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(mode)
    temporary.replace(path)


def _windows_python(paths: InstallPaths, *, windowed: bool = False) -> Path:
    name = "pythonw.exe" if windowed else "python.exe"
    return paths.app_dir / ".venv" / "Scripts" / name


def _install_windows_runtime(paths: InstallPaths, progress: Progress) -> None:
    python = _windows_python(paths)
    if not python.is_file():
        progress("Creating the private Python runtime...")
        uv = shutil.which("uv")
        if uv:
            result = _run(
                [uv, "venv", str(paths.app_dir / ".venv"), "--python", sys.executable],
                check=False,
                capture=True,
            )
        else:
            result = _run(
                [sys.executable, "-m", "venv", str(paths.app_dir / ".venv")],
                check=False,
                capture=True,
            )
        if result.returncode != 0:
            raise InstallError("Could not create Snipaster's private Python runtime.")

    progress("Installing the Windows graphical runtime...")
    uv = shutil.which("uv")
    command = (
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "PyQt5==5.15.11",
            "PyQt5-Qt5==5.15.2",
        ]
        if uv
        else [
            str(python),
            "-m",
            "pip",
            "install",
            "PyQt5==5.15.11",
            "PyQt5-Qt5==5.15.2",
        ]
    )
    result = _run(command, check=False, capture=True)
    if result.returncode != 0:
        details = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise InstallError(
            "Could not install PyQt5 into Snipaster's private runtime."
            + (f"\n{details}" if details else "")
        )


def install_windows_application_files(
    source_dir: Path,
    paths: InstallPaths,
    progress: Progress,
    *,
    install_runtime: bool = True,
) -> None:
    app_source = source_dir / "snipaster.py"
    icon_source = source_dir / "assets" / "snipaster-icon.svg"
    if not app_source.is_file() or not icon_source.is_file():
        raise InstallError("Snipaster application files are missing from the source tree.")

    progress("Installing the Snipaster application...")
    paths.app_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(app_source, paths.app_dir / "snipaster.py")
    shutil.copy2(icon_source, paths.icon)
    if install_runtime:
        _install_windows_runtime(paths, progress)

    pythonw = _windows_python(paths, windowed=True) if install_runtime else Path(sys.executable)
    app = paths.app_dir / "snipaster.py"
    launcher = f'@echo off\n"{pythonw}" "{app}" %*\n'
    compatibility = f'@echo off\ncall "{paths.launcher}" capture %*\n'
    _write_text(paths.launcher, launcher)
    _write_text(paths.compatibility_launcher, compatibility)

    progress("Creating Desktop and Start Menu launchers...")
    annotate = f'@echo off\ncall "{paths.launcher}" annotate %*\n'
    tray = f'@echo off\ncall "{paths.launcher}" tray\n'
    _write_text(paths.desktop_entry, annotate)
    _write_text(paths.applications_entry, annotate)
    _write_text(paths.tray_autostart, tray)


def install_application_files(
    source_dir: Path,
    paths: InstallPaths,
    progress: Progress,
) -> None:
    if os.name == "nt":
        install_windows_application_files(source_dir, paths, progress)
        return
    app_source = source_dir / "snipaster.py"
    icon_source = source_dir / "assets" / "snipaster-icon.svg"
    if not app_source.is_file():
        raise InstallError(f"Application source is missing: {app_source}")
    if not icon_source.is_file():
        raise InstallError(f"Application icon is missing: {icon_source}")

    progress("Installing the Snipaster application...")
    paths.app_dir.mkdir(parents=True, exist_ok=True)
    paths.bin_dir.mkdir(parents=True, exist_ok=True)
    paths.icon.parent.mkdir(parents=True, exist_ok=True)

    installed_app = paths.app_dir / "snipaster.py"
    installed_icon = paths.app_dir / "snipaster-icon.svg"
    shutil.copy2(app_source, installed_app)
    shutil.copy2(icon_source, installed_icon)
    shutil.copy2(icon_source, paths.icon)
    installed_app.chmod(0o755)
    installed_icon.chmod(0o644)
    paths.icon.chmod(0o644)

    launcher = f"""#!/bin/sh
exec /usr/bin/python3 {shlex.quote(str(installed_app))} "$@"
"""
    compatibility = f"""#!/bin/sh
exec {shlex.quote(str(paths.launcher))} capture "$@"
"""
    _write_text(paths.launcher, launcher, 0o755)
    _write_text(paths.compatibility_launcher, compatibility, 0o755)

    progress("Creating the app-menu and desktop capture icons...")
    entry = make_application_entry(paths)
    _write_text(paths.applications_entry, entry, 0o755)
    _write_text(paths.desktop_entry, entry, 0o755)
    _trust_desktop_entry(paths.desktop_entry)

    progress("Enabling the one-click capture icon at login...")
    _write_text(paths.tray_autostart, make_tray_autostart_entry(paths), 0o644)

    update_desktop_database = shutil.which("update-desktop-database")
    if update_desktop_database:
        _run(
            [update_desktop_database, str(paths.applications_entry.parent)],
            check=False,
            capture=True,
        )
    gtk_update_icon_cache = shutil.which("gtk-update-icon-cache")
    icon_root = paths.icon.parents[2]
    if gtk_update_icon_cache and icon_root.is_dir():
        _run(
            [gtk_update_icon_cache, "-f", "-t", str(icon_root)],
            check=False,
            capture=True,
        )


def _trust_desktop_entry(path: Path) -> None:
    gio = shutil.which("gio")
    if not gio:
        return
    _run(
        [gio, "set", str(path), "metadata::trusted", "true"],
        check=False,
        capture=True,
    )


def parse_gvariant_string_array(value: str) -> list[str]:
    """Parse the output of `gsettings get ... custom-keybindings`."""

    cleaned = value.strip()
    if cleaned.startswith("@as "):
        cleaned = cleaned[4:].strip()
    try:
        parsed = ast.literal_eval(cleaned)
    except (ValueError, SyntaxError) as exc:
        raise InstallError(f"Could not parse GNOME keybindings: {value}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise InstallError(f"Unexpected GNOME keybinding value: {value}")
    return parsed


def parse_gvariant_string(value: str) -> str:
    cleaned = value.strip()
    try:
        parsed = ast.literal_eval(cleaned)
    except (ValueError, SyntaxError):
        return cleaned
    return parsed if isinstance(parsed, str) else cleaned


def gvariant_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _gsettings_get(schema: str, key: str) -> str:
    result = _run(["gsettings", "get", schema, key], capture=True)
    return result.stdout.strip()


def _gsettings_set(schema: str, key: str, value: str) -> None:
    _run(["gsettings", "set", schema, key, value])


def setup_gnome_hotkey(
    paths: InstallPaths, binding_name: str, command: str, binding: str
) -> None:
    raw = _gsettings_get(GNOME_MEDIA_SCHEMA, "custom-keybindings")
    bindings = parse_gvariant_string_array(raw)
    chosen: Optional[str] = None

    for path in bindings:
        schema = f"{GNOME_MEDIA_SCHEMA}.custom-keybinding:{path}"
        try:
            existing_name = parse_gvariant_string(_gsettings_get(schema, "name"))
            configured = parse_gvariant_string(_gsettings_get(schema, "command"))
        except subprocess.CalledProcessError:
            continue
        if existing_name == binding_name or configured == command:
            chosen = path
            break

    if chosen is None:
        used = set(bindings)
        index = 0
        while f"{GNOME_BINDING_BASE}{index}/" in used:
            index += 1
        chosen = f"{GNOME_BINDING_BASE}{index}/"
        bindings.append(chosen)
        _gsettings_set(GNOME_MEDIA_SCHEMA, "custom-keybindings", repr(bindings))

    schema = f"{GNOME_MEDIA_SCHEMA}.custom-keybinding:{chosen}"
    _gsettings_set(schema, "name", gvariant_string(binding_name))
    _gsettings_set(schema, "command", gvariant_string(command))
    _gsettings_set(schema, "binding", gvariant_string(binding))


def merge_xbindkeys_config(
    existing: str, capture_command: str, annotate_command: Optional[str] = None
) -> str:
    """Install one idempotent managed block without deleting user shortcuts."""

    pattern = re.compile(
        rf"\n?{re.escape(MANAGED_XBINDKEYS_START)}.*?"
        rf"{re.escape(MANAGED_XBINDKEYS_END)}\n?",
        flags=re.DOTALL,
    )
    preserved = pattern.sub("\n", existing).rstrip()
    block = (
        f'{MANAGED_XBINDKEYS_START}\n'
        f'"{capture_command}"\n'
        "  F1\n"
        + (
            f'"{annotate_command}"\n'
            "  F2\n"
            if annotate_command
            else ""
        )
        + f"{MANAGED_XBINDKEYS_END}"
    )
    return f"{preserved}\n\n{block}\n" if preserved else f"{block}\n"


def setup_x11_hotkey(paths: InstallPaths) -> str:
    config = paths.home / ".xbindkeysrc"
    existing = config.read_text(encoding="utf-8") if config.is_file() else ""
    capture_command = f"{paths.launcher} capture"
    annotate_command = f"{paths.launcher} annotate"
    _write_text(
        config,
        merge_xbindkeys_config(existing, capture_command, annotate_command),
        0o600,
    )

    autostart = paths.home / ".config" / "autostart" / "snipaster-xbindkeys.desktop"
    _write_text(
        autostart,
        """[Desktop Entry]
Version=1.0
Type=Application
Name=Snipaster X11 Hotkey
Comment=Start xbindkeys for the Snipaster F1 shortcut
Exec=xbindkeys
Terminal=false
NoDisplay=true
StartupNotify=false
X-GNOME-Autostart-enabled=true
""",
        0o644,
    )
    _run(["pkill", "-x", "xbindkeys"], check=False, capture=True)
    subprocess.Popen(
        ["xbindkeys"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return "F1 capture and F2 annotation through xbindkeys"


def configure_hotkey(paths: InstallPaths, progress: Progress) -> str:
    if os.name == "nt":
        progress("Configuring F1 capture and F2 annotation through the tray process...")
        return "F1 capture and F2 annotation through the Windows tray process"
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if not session:
        session = "wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11"
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    gnome = "gnome" in desktop or "ubuntu" in desktop

    if gnome and shutil.which("gsettings"):
        progress("Binding F1 to Snipaster in GNOME...")
        try:
            setup_gnome_hotkey(
                paths,
                "Snipaster Capture",
                f"{paths.launcher} capture",
                "F1",
            )
            setup_gnome_hotkey(
                paths,
                "Snipaster Annotate",
                f"{paths.launcher} annotate",
                "F2",
            )
        except (subprocess.CalledProcessError, InstallError) as exc:
            raise InstallError(
                "GNOME rejected the F1 shortcut configuration. "
                "Run the installer inside your logged-in desktop session."
            ) from exc
        (
            paths.home
            / ".config"
            / "autostart"
            / "snipaster-xbindkeys.desktop"
        ).unlink(missing_ok=True)
        return "F1 capture and F2 annotation through GNOME custom shortcuts"

    if session != "wayland":
        progress("Binding F1 to Snipaster through xbindkeys...")
        return setup_x11_hotkey(paths)

    progress(
        "Desktop launcher installed; this Wayland compositor needs a manual F1 binding."
    )
    return f"manual compositor binding to: {paths.launcher} capture"


def start_tray(paths: InstallPaths) -> bool:
    if os.name == "nt":
        try:
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", str(paths.launcher), "tray"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS,
            )
        except OSError:
            return False
        return True
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        subprocess.Popen(
            [str(paths.launcher), "tray"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def validate_installation(paths: InstallPaths) -> None:
    required = (
        paths.app_dir / "snipaster.py",
        paths.launcher,
        paths.compatibility_launcher,
        paths.icon,
        paths.applications_entry,
        paths.desktop_entry,
        paths.tray_autostart,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise InstallError("Installation validation failed; missing: " + ", ".join(missing))

    python = _windows_python(paths) if os.name == "nt" else Path("/usr/bin/python3")
    if os.name == "nt" and not python.is_file():
        python = Path(sys.executable)
    result = _run(
        [str(python), "-m", "py_compile", str(paths.app_dir / "snipaster.py")],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        raise InstallError("Installed application failed Python syntax validation.")


def install(
    progress: Progress = print,
    *,
    source_dir: Path = SOURCE_DIR,
    home: Optional[Path] = None,
    install_system_packages: bool = True,
    launch_tray: bool = True,
) -> InstallationResult:
    """Install Snipaster and return the resulting user-level paths."""

    if os.name != "nt" and os.geteuid() == 0 and home is None:
        raise InstallError(
            "Run Snipaster as your normal desktop user, not with sudo."
        )
    paths = install_paths(home)

    if install_system_packages and os.name != "nt":
        progress("Checking the Ubuntu desktop runtime...")
        ensure_packages(progress)

    if os.name == "nt":
        install_windows_application_files(
            source_dir, paths, progress, install_runtime=home is None
        )
    else:
        install_application_files(source_dir, paths, progress)
    hotkey = configure_hotkey(paths, progress) if home is None else "not configured in test mode"
    progress("Validating the installed application...")
    validate_installation(paths)
    tray_started = start_tray(paths) if launch_tray and home is None else False
    progress("Snipaster is ready.")
    return InstallationResult(paths, hotkey, tray_started)


__all__ = [
    "InstallError",
    "InstallationResult",
    "InstallPaths",
    "desktop_exec",
    "install",
    "install_application_files",
    "install_paths",
    "make_application_entry",
    "merge_xbindkeys_config",
    "missing_packages",
    "parse_gvariant_string_array",
    "prepare_privileges",
]
