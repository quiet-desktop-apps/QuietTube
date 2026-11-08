"""Explicit, independent website-session setup for native playback."""
from gi.repository import GLib, Gio, Gtk

from .browsers import suggested_profile
from .tasks import ExtractorTasks


class PlaybackConnectionWindow(Gtk.Window):
    def __init__(self, parent, store, updated):
        super().__init__(title="Connect playback", transient_for=parent, modal=True)
        from .ui import box, button, label
        self.store, self.updated = store, updated
        self.closed = False
        self.source = {}
        self.tasks = ExtractorTasks(lambda result: GLib.idle_add(self.on_result, result))
        self.set_default_size(580, 660)
        self.connect("close-request", self.on_close)
        content = box(spacing=14)
        for setter in (content.set_margin_start, content.set_margin_end, content.set_margin_top, content.set_margin_bottom):
            setter(24)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(content)
        self.set_child(scroll)
        content.append(label("Connect YouTube for mpv playback", "subheading", True))
        content.append(label("Keep personal OAuth for your dashboard and Likes. This separate session is used only "
                             "for playback while personal OAuth is selected. In browser-session account mode, "
                             "playback continues using that account's session.", "muted", True))
        content.append(label("1. Sign into YouTube in your browser.\n2. Select that browser below and save its session.\n"
                             "3. Close the browser, return to QuietTube and press Play.", "small", True))
        content.append(button("Open YouTube sign-in", self.open_sign_in))
        self.names = ["chromium", "chrome", "brave", "edge", "firefox", "vivaldi", "opera"]
        self.browser = Gtk.DropDown.new_from_strings(["Chromium", "Google Chrome", "Brave", "Microsoft Edge", "Firefox", "Vivaldi", "Opera"])
        saved = store.get("playback_source", store.get("account_source", {}))
        if saved.get("browser") in self.names:
            self.browser.set_selected(self.names.index(saved["browser"]))
        self.profile = Gtk.Entry(placeholder_text="Optional browser profile name or full path")
        def profile_hint(*_):
            name = self.names[self.browser.get_selected()]
            self.profile.set_text((saved.get("profile", "") if saved.get("browser") == name else "") or suggested_profile(name))
        profile_hint()
        self.browser.connect("notify::selected", profile_hint)
        content.append(self.browser)
        content.append(self.profile)
        content.append(label("Saving reads that browser's cookies and keeps only YouTube cookies in a private local "
                             "file outside the project. They are sent to YouTube for playback, never committed to GitHub. "
                             "YouTube can expire or reject the session; saving it does not prove playback works.", "small", True))
        self.actions = box(spacing=8)
        self.connect_button = button("Save browser session for playback", self.connect_browser, "suggested-action")
        self.actions.append(self.connect_button)
        self.actions.append(button("Import YouTube cookies.txt instead", self.choose_cookies))
        self.remove_button = button("Remove playback session", self.remove_session)
        self.remove_button.set_sensitive(store.playback_cookie_path.exists())
        self.actions.append(self.remove_button)
        content.append(self.actions)
        self.progress = label("Session saved. Press Play to test it." if store.get("playback_session_enabled", False)
                              and store.playback_cookie_path.exists() else "No separate playback session saved.", "small", True)
        content.append(self.progress)
        content.append(button("Close", self.close))

    def open_sign_in(self):
        try:
            Gio.AppInfo.launch_default_for_uri("https://www.youtube.com/", None)
        except GLib.Error:
            self.progress.set_text("Could not open your browser. Open youtube.com and sign in there.")

    def connect_browser(self):
        self.connect_session({"browser": self.names[self.browser.get_selected()],
                              "profile": self.profile.get_text().strip()})

    def connect_session(self, source):
        self.source = {key: value for key, value in source.items() if key in {"browser", "profile"}}
        if "cookie_file" in source:
            self.source = {"browser": "cookie-file"}
        self.actions.set_sensitive(False)
        self.progress.set_text("Reading and saving the selected YouTube session…")
        self.tasks.submit({"action": "playback_connect", "session": str(self.store.playback_cookie_path), **source})

    def choose_cookies(self):
        chooser = Gtk.FileChooserNative(title="Choose exported YouTube cookies", transient_for=self,
                                         action=Gtk.FileChooserAction.OPEN, accept_label="Import", cancel_label="Cancel")
        def response(dialog, result):
            if not self.closed and result == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                path = file.get_path() if file else None
                if path:
                    self.connect_session({"cookie_file": path})
            dialog.destroy()
        chooser.connect("response", response)
        chooser.show()

    def on_result(self, result):
        if self.closed or result.generation != self.tasks.generation:
            return False
        self.actions.set_sensitive(True)
        if result.error:
            self.progress.set_text(result.error)
        elif (result.data or {}).get("playback_session_saved"):
            self.store.set("playback_session_enabled", True)
            self.store.set("playback_source", self.source)
            self.remove_button.set_sensitive(True)
            self.progress.set_text("Session saved. You can close the browser now. Close this dialog and press Play "
                                   "to retry at the saved position. Your OAuth dashboard connection is unchanged.")
            self.updated()
        else:
            self.progress.set_text("No playback session was confirmed. Please retry.")
        return False

    def remove_session(self):
        self.tasks.cancel()
        self.store.set("playback_session_enabled", False)
        self.store.playback_cookie_path.unlink(missing_ok=True)
        self.store.set("playback_source", {})
        self.remove_button.set_sensitive(False)
        self.progress.set_text("Playback session removed. OAuth account access and your queue are unchanged.")
        self.updated()

    def on_close(self, *_):
        self.closed = True
        self.tasks.close()
        return False
