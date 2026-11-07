"""Profile location hints only; cookie access happens on explicit Connect."""
from pathlib import Path


def has_cookie_database(root: Path, browser: str) -> bool:
    """Check filenames only. Empty/stale installation folders are not profiles."""
    patterns = ("cookies.sqlite", "*/cookies.sqlite") if browser == "firefox" else (
        "Cookies", "Network/Cookies", "*/Cookies", "*/Network/Cookies")
    return any(path.is_file() for pattern in patterns for path in root.glob(pattern))


def suggested_profile(browser: str, home: Path | None = None) -> str:
    home = home or Path.home()
    standard = {
        "chromium": ".config/chromium", "chrome": ".config/google-chrome",
        "brave": ".config/BraveSoftware/Brave-Browser", "edge": ".config/microsoft-edge",
        "firefox": ".mozilla/firefox", "vivaldi": ".config/vivaldi", "opera": ".config/opera",
    }
    if browser not in standard or has_cookie_database(home / standard[browser], browser):
        return ""
    alternatives = {
        "chromium": ["snap/chromium/common/chromium", ".var/app/org.chromium.Chromium/config/chromium"],
        "chrome": [".var/app/com.google.Chrome/config/google-chrome"],
        "brave": [".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"],
        "edge": [".var/app/com.microsoft.Edge/config/microsoft-edge"],
        "firefox": ["snap/firefox/common/.mozilla/firefox", ".var/app/org.mozilla.firefox/.mozilla/firefox"],
        "vivaldi": [".var/app/com.vivaldi.Vivaldi/config/vivaldi"],
    }
    for relative in alternatives.get(browser, []):
        path = home / relative
        if has_cookie_database(path, browser):
            return str(path)
    return ""
