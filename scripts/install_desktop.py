"""Install this checkout's launcher and scalable icon for the current Linux user."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

APP_ID = "ch.aboimpinto.QuietTube"


def desktop_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def exec_argument(value: str) -> str:
    # Desktop Exec field quoting is not shell quoting. Escape its reserved
    # characters, then the outer desktop-entry string layer; %% is a literal %.
    escaped = "".join("\\" + char if char in '\\"`$' else char for char in value)
    return '"' + desktop_string(escaped).replace("%", "%%") + '"'


def install(project: Path, data_home: Path) -> Path:
    project = project.resolve()
    launcher = project / "run.sh"
    if not launcher.is_file():
        raise FileNotFoundError("QuietTube run.sh was not found")
    apps = data_home / "applications"
    icons = data_home / "icons/hicolor/scalable/apps"
    apps.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / "quiettube/icons" / f"{APP_ID}.svg", icons / f"{APP_ID}.svg")
    # Use a direct icon for the launcher as well: pre-existing broken theme
    # caches must not leave this application with a generic dock icon.
    direct_icon = data_home / "icons" / f"{APP_ID}.svg"
    shutil.copyfile(project / "quiettube/icons" / f"{APP_ID}.svg", direct_icon)
    entry = apps / f"{APP_ID}.desktop"
    entry.write_text(
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=QuietTube\n"
        "Comment=Your YouTube feeds and queue, in a lightweight native player\n"
        f"Exec={exec_argument(str(launcher))}\n"
        f"Path={desktop_string(str(project))}\n"
        f"Icon={desktop_string(str(direct_icon.resolve()))}\n"
        "Terminal=false\n"
        "StartupNotify=true\n"
        f"StartupWMClass={APP_ID}\n"
        "Categories=AudioVideo;Video;Player;\n"
        "Keywords=YouTube;video;player;queue;\n",
        encoding="utf-8",
    )
    entry.chmod(0o644)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-home", type=Path, default=Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))))
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    entry = install(project, args.data_home)
    if shutil.which("desktop-file-validate"):
        subprocess.run(["desktop-file-validate", str(entry)], check=True)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(entry.parent)], capture_output=True)
    if shutil.which("gtk-update-icon-cache"):
        refreshed = subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(args.data_home / "icons/hicolor")], capture_output=True)
        if refreshed.returncode:
            print("Existing icon theme cache could not be refreshed; the launcher uses its SVG directly.")
    print(f"Installed launcher: {entry}")
    print("Open QuietTube from Applications, then right-click its dock icon and choose Pin to Dash / Add to Favorites.")


if __name__ == "__main__":
    main()
