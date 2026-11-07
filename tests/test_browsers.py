from quiettube.browsers import suggested_profile


def test_snap_chromium_profile_is_suggested_when_native_missing(tmp_path):
    snap = tmp_path / "snap/chromium/common/chromium"
    (snap / "Default").mkdir(parents=True)
    (snap / "Default/Cookies").touch()
    assert suggested_profile("chromium", tmp_path) == str(snap)
    (tmp_path / ".config/chromium").mkdir(parents=True)
    # An empty native folder must not hide the real Snap installation.
    assert suggested_profile("chromium", tmp_path) == str(snap)
    native = tmp_path / ".config/chromium/Default/Network"
    native.mkdir(parents=True)
    (native / "Cookies").touch()
    assert suggested_profile("chromium", tmp_path) == ""


def test_flatpak_and_snap_firefox_locations(tmp_path):
    flatpak = tmp_path / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"
    (flatpak / "Default").mkdir(parents=True)
    (flatpak / "Default/Cookies").touch()
    assert suggested_profile("brave", tmp_path) == str(flatpak)
    firefox = tmp_path / "snap/firefox/common/.mozilla/firefox"
    (firefox / "example.default").mkdir(parents=True)
    (firefox / "example.default/cookies.sqlite").touch()
    assert suggested_profile("firefox", tmp_path) == str(firefox)
    assert suggested_profile("unknown", tmp_path) == ""


def test_empty_alternative_folders_are_not_suggested(tmp_path):
    (tmp_path / "snap/chromium/common/chromium").mkdir(parents=True)
    assert suggested_profile("chromium", tmp_path) == ""
