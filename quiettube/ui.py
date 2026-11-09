from __future__ import annotations

from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .controller import PlaybackController
from .history_sync import HistorySync
from .browsers import suggested_profile
from .models import Video, duration_label, finite_seconds, playlist_url, published_label, publication_sort_key, video_id
from .player import MpvPlayer
from .diagnostics import PlaybackLog
from .storage import Store
from .tasks import ExtractorTasks
from .thumbnails import Thumbnails

APP_ID = "ch.aboimpinto.QuietTube"
VIDEO_CARD_WIDTH = 400
ACCOUNT_OPERATIONS = {"connect", "oauth_configure", "oauth_connect", "oauth_forget"}

DEMO_VIDEOS = [
    Video("jNQXAC9IVRw", "An afternoon outside: finding a slower rhythm", "Everyday stories", 842),
    Video("aqz-KE-bpKQ", "Big Buck Bunny • an open animation project", "Blender Foundation", 596),
    Video("ScMzIvxBSi4", "How a small idea becomes a useful tool", "The workshop", 1254),
    Video("dQw4w9WgXcQ", "Music for a quiet working afternoon", "Listening room", 212),
    Video("M7lc1UVf-VE", "A closer look at the things we build", "Curious minds", 932),
    Video("YE7VzlLtp-4", "Stories told through animation", "Open cinema", 888),
]


def label(text, css="", wrap=False):
    widget = Gtk.Label(label=text, xalign=0)
    if css:
        for name in css.split():
            widget.add_css_class(name)
    widget.set_wrap(wrap)
    if wrap:
        widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


def button(text, callback, css="", tooltip=""):
    widget = Gtk.Button(label=text)
    widget.connect("clicked", lambda *_: callback())
    if css:
        widget.add_css_class(css)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    return widget


def box(vertical=True, spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


def clear(container):
    child = container.get_first_child()
    while child:
        following = child.get_next_sibling()
        container.remove(child)
        child = following


class VideoThumbnail(Gtk.Picture):
    """Reserve a 16:9 preview at every card width, including before images load."""

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return (220, 320, -1, -1)
        height = round((for_size if for_size >= 0 else 220) * 9 / 16)
        return (height, height, -1, -1)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, directory: Path, demo=False):
        super().__init__(application=app, title="QuietTube")
        self.set_icon_name(APP_ID)
        self.set_default_size(1380, 880)
        self.set_size_request(1000, 660)
        self.demo = demo
        self.closed = False
        self.store = Store(directory)
        self.playback_log = PlaybackLog(self.store.directory / "logs")
        self.player = MpvPlayer(lambda event: GLib.idle_add(self.on_player, event), log=self.playback_log)
        self.history_sync = HistorySync(self.store, GLib.idle_add, self.history_status_changed)
        self.controller = PlaybackController(self.store, self.player, self.refresh_transport, self.history_sync.observe)
        self.tasks = ExtractorTasks(lambda result: GLib.idle_add(self.on_result, result))
        self.rating_tasks = ExtractorTasks(lambda result: GLib.idle_add(self.on_like_result, result))
        self.like_pending = None
        self.liked_ids = set()
        self.like_buttons = {}
        self.play_choice = None
        self.thumbnails = Thumbnails(GLib.idle_add)
        self.feed = "home"
        self.query = ""
        self.page = 0
        self.pending = ""
        self.videos = []
        self.feed_videos = []
        self.watched_ids = set()
        self.has_more = False
        self.queue_signature = None
        self.last_selected = None
        self.account_window = None
        self.oauth_sign_in_shortcut = None
        self.playback_help_window = None
        self.playback_connection_window = None
        self.oauth_verified = False
        self.page_tokens = {0: ""}
        self.busy = False
        self._build()
        self.connect("close-request", self.on_close)
        self.checkpoint_timer = GLib.timeout_add_seconds(5, self.checkpoint)
        if demo:
            self.controller.queue.add(DEMO_VIDEOS[2])
            self.controller.queue.add(DEMO_VIDEOS[4])
            self.controller.queue.add(DEMO_VIDEOS[5])
            self.show_videos(DEMO_VIDEOS)
            self.set_status("Preview data · Queue editing works; playback and account access are disabled.")
        else:
            self.show_empty("Your videos. A little more breathing room.",
                            "Connect YouTube for your home feed and subscriptions, or search for a video to get started.")
            if self.account_available():
                self.load_feed("home")
        self.refresh_transport()
        if self.store.load_warning:
            self.set_status(self.store.load_warning, True)

    def _build(self):
        header = Gtk.HeaderBar()
        header.set_title_widget(label("QuietTube", "brand"))
        header.pack_start(label("LESS BROWSER. MORE VIDEO.", "eyebrow"))
        self.account_button = button("Connect YouTube", self.open_account)
        header.pack_end(self.account_button)
        self.playback_connection_button = button("Connect playback", self.open_playback_connection)
        header.pack_end(self.playback_connection_button)
        self.set_titlebar(header)

        root = box(spacing=0)
        self.set_child(root)
        body = box(False, 0)
        body.set_vexpand(True)
        root.append(body)
        sidebar = box(spacing=7)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(170, -1)
        body.append(sidebar)
        sidebar.append(label("YOUR SPACE", "eyebrow"))
        self.nav = {}
        for key, title in [("home", "⌂  Home"), ("subscriptions", "▤  Subscriptions"),
                           ("later", "◷  Watch Later"), ("liked", "♡  Liked videos"), ("history", "↶  Local history")]:
            nav = button(title, lambda key=key: self.load_feed(key))
            nav.set_halign(Gtk.Align.FILL)
            self.nav[key] = nav
            sidebar.append(nav)
        spacer = box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)
        sidebar.append(label("One video at a time.", "muted small"))
        sidebar.append(label("Your queue stays here\nwhen you close the app.", "muted small", True))
        sidebar.append(label("NATIVE PLAYER", "pill"))

        main = box(spacing=12)
        main.set_hexpand(True)
        for setter in (main.set_margin_start, main.set_margin_end, main.set_margin_top):
            setter(22)
        body.append(main)
        search_row = box(False)
        self.search_entry = Gtk.Entry(placeholder_text="Search YouTube or paste a video / playlist link")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("activate", lambda *_: self.search())
        search_row.append(self.search_entry)
        search_row.append(button("Paste link", self.paste_link, tooltip="Open a video link from the clipboard"))
        search_row.append(button("Search", self.search, "suggested-action"))
        main.append(search_row)
        title_row = box(False)
        titles = box(spacing=3)
        titles.set_hexpand(True)
        self.feed_title = label("Your home feed", "heading")
        self.feed_caption = label("Choose something good. Watch it on your terms.", "muted", True)
        titles.append(self.feed_title)
        titles.append(self.feed_caption)
        title_row.append(titles)
        self.spinner = Gtk.Spinner()
        title_row.append(self.spinner)
        self.refresh_button = button("Refresh", self.reload)
        title_row.append(self.refresh_button)
        self.cancel_button = button("Cancel", self.cancel_request)
        self.cancel_button.set_visible(False)
        title_row.append(self.cancel_button)
        main.append(title_row)
        self.wall_controls = box(False)
        self.wall_order = Gtk.DropDown.new_from_strings(["Newest first", "YouTube order"])
        self.wall_order.set_selected(0 if self.store.get("wall_newest", True) else 1)
        self.wall_order.set_tooltip_text("Sort the loaded page by publication date; unknown dates appear last")
        self.hide_watched = Gtk.CheckButton(label="Hide watched here")
        self.hide_watched.set_active(bool(self.store.get("wall_hide_watched", True)))
        self.hide_watched.set_tooltip_text("Hide completed videos from local history; YouTube history is not changed")
        self.wall_order.connect("notify::selected", self.wall_options_changed)
        self.hide_watched.connect("toggled", self.wall_options_changed)
        self.wall_controls.append(self.wall_order)
        self.wall_controls.append(self.hide_watched)
        self.wall_controls.append(label("Applies to this page", "muted small"))
        main.append(self.wall_controls)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        self.feed_container = box(spacing=12)
        scroller.set_child(self.feed_container)
        main.append(scroller)
        pagination = box(False)
        self.previous_button = button("← Previous", lambda: self.change_page(-1))
        self.next_button = button("Next page →", lambda: self.change_page(1))
        self.page_label = label("", "muted small")
        pagination.append(self.previous_button)
        pagination.append(self.page_label)
        pagination.append(self.next_button)
        pagination.set_margin_bottom(12)
        main.append(pagination)

        queue_panel = box(spacing=12)
        queue_panel.add_css_class("queue-panel")
        queue_panel.set_size_request(320, -1)
        body.append(queue_panel)
        self.queue_title = label("Up next", "subheading")
        queue_panel.append(self.queue_title)
        queue_panel.append(label("Insert, reorder, or save it for later.", "muted small"))
        self.queue_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.queue_list.connect("row-selected", self.queue_selected)
        queue_scroll = Gtk.ScrolledWindow()
        queue_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        queue_scroll.set_vexpand(True)
        queue_scroll.set_child(self.queue_list)
        queue_panel.append(queue_scroll)
        queue_tools = box(False, 5)
        queue_tools.append(button("↑", lambda: self.move_selected(-1), tooltip="Move selected video up"))
        queue_tools.append(button("↓", lambda: self.move_selected(1), tooltip="Move selected video down"))
        queue_tools.append(button("Remove", self.remove_selected))
        queue_panel.append(queue_tools)
        position_row = box(False, 5)
        position_row.append(label("Move to", "small"))
        self.move_position = Gtk.SpinButton.new_with_range(1, 1000, 1)
        position_row.append(self.move_position)
        position_row.append(button("Move", self.move_to_position))
        queue_panel.append(position_row)
        self.queue_play_button = button("Play queue", self.play, "suggested-action")
        queue_panel.append(self.queue_play_button)
        queue_panel.append(label("Close video: done & next. Pause to resume later.", "muted small", True))
        queue_panel.append(label("Only the current video is buffered.", "muted small"))

        self.status = label("Ready", "status", True)
        status_row = box(False, 8)
        self.status.set_hexpand(True)
        status_row.append(self.status)
        self.playback_help_button = button("Playback help", self.open_playback_help)
        self.playback_help_button.set_visible(False)
        status_row.append(self.playback_help_button)
        self.skip_failed_button = button("Skip failed video", self.skip)
        self.skip_failed_button.set_visible(False)
        status_row.append(self.skip_failed_button)
        root.append(status_row)
        transport = box(False, 14)
        transport.add_css_class("transport")
        now = box(spacing=3)
        now.set_hexpand(True)
        now.append(label("NOW PLAYING", "eyebrow"))
        self.now_title = label("Pick your next video", "subheading")
        self.now_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.now_title.set_max_width_chars(55)
        now.append(self.now_title)
        self.now_detail = label("Playback opens in a lightweight mpv window.", "muted small")
        now.append(self.now_detail)
        self.history_status = label("History sharing on" if self.store.get("share_watch_history", False) else "History sharing off", "muted small")
        self.history_status.set_ellipsize(Pango.EllipsizeMode.END)
        self.history_status.set_max_width_chars(55)
        now.append(self.history_status)
        transport.append(now)
        transport.append(button("−10s", lambda: self.player.command(["seek", -10, "relative"])))
        self.play_button = button("Play", self.play, "suggested-action")
        transport.append(self.play_button)
        transport.append(button("+10s", lambda: self.player.command(["seek", 10, "relative"])))
        transport.append(button("Next", self.skip))
        stop_button = button("Stop", self.controller.stop)
        stop_button.set_tooltip_text("Stop and keep this video for later. Closing the mpv window finishes it and plays the next.")
        transport.append(stop_button)
        self.quality = Gtk.DropDown.new_from_strings(["480p", "720p", "1080p", "1440p", "2160p"])
        self.quality.set_selected([480, 720, 1080, 1440, 2160].index(self.controller.height))
        self.quality.set_tooltip_text("Maximum quality for the next video")
        self.quality.connect("notify::selected", self.quality_changed)
        transport.append(self.quality)
        self.reload_video_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload video at the current position (use if the picture freezes)")
        self.reload_video_button.update_property([Gtk.AccessibleProperty.LABEL], ["Reload video"])
        self.reload_video_button.connect("clicked", lambda *_: self.reload_video())
        transport.append(self.reload_video_button)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume.set_value(self.controller.volume)
        self.volume.set_size_request(85, -1)
        self.volume.set_tooltip_text("Volume")
        self.volume.connect("value-changed", self.volume_changed)
        transport.append(self.volume)
        root.append(transport)

    def history_status_changed(self, text):
        if not self.closed:
            self.history_status.set_text(text)

    def history_sharing_changed(self, enabled):
        self.history_sync.reset()
        self.store.set("share_watch_history", enabled)
        self.history_status_changed("History sharing on" if enabled else "History sharing off")
        if enabled:
            self.controller.observation("share")

    def set_status(self, text, error=False):
        self.status.set_text(text)
        if error:
            self.status.add_css_class("error")
        else:
            self.status.remove_css_class("error")

    def set_busy(self, busy):
        self.busy = busy
        self.spinner.set_spinning(busy)
        self.cancel_button.set_visible(busy)
        self.refresh_button.set_sensitive(not busy)
        self.previous_button.set_sensitive(not busy and self.page > 0)
        self.next_button.set_sensitive(not busy and self.has_more)
        # A session import is atomic; prevent a second account mutation until completion/cancel.
        if self.account_window:
            self.account_actions.set_sensitive(not busy)
            self.oauth_actions.set_sensitive(not busy)
            if self.oauth_sign_in_shortcut:
                self.oauth_sign_in_shortcut.set_sensitive(not busy)

    def show_empty(self, title, message, reset=True):
        self.thumbnails.new_page()
        self.like_buttons.clear()
        self.liked_ids.clear()
        clear(self.feed_container)
        self.videos = []
        if reset:
            self.has_more = False
            self.feed_videos = []
        self.wall_controls.set_visible(self.feed in {"home", "subscriptions"})
        empty = box(spacing=16)
        empty.add_css_class("empty")
        empty.append(label("▷", "heading"))
        empty.append(label(title, "subheading", True))
        empty.append(label(message, "muted", True))
        if not self.demo and not self.account_available():
            connect = button("Connect your YouTube account", self.open_account, "suggested-action")
            connect.set_halign(Gtk.Align.START)
            empty.append(connect)
        self.feed_container.append(empty)
        self.update_pagination()

    def show_videos(self, videos):
        self.feed_videos = list(videos)
        self.watched_ids = self.store.completed_ids()
        wall = self.feed in {"home", "subscriptions"}
        self.wall_controls.set_visible(wall)
        if wall:
            if self.hide_watched.get_active():
                videos = [video for video in videos if video.id not in self.watched_ids]
            if self.wall_order.get_selected() == 0:
                videos = sorted(videos, key=publication_sort_key, reverse=True)
        self.thumbnails.new_page()
        self.like_buttons.clear()
        self.liked_ids.intersection_update(video.id for video in videos)
        if self.feed == "liked" and not self.demo:
            self.liked_ids.update(video.id for video in videos)
        clear(self.feed_container)
        self.videos = videos
        if not videos:
            if self.feed_videos:
                self.show_empty("You've watched this page", "Show watched videos above, or use Next page to browse more.", reset=False)
            else:
                self.show_empty("Nothing to show here yet", "Try a search, another feed, or reconnect if your session has expired.", reset=False)
            return
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
        flow.set_min_children_per_line(1)
        flow.set_max_children_per_line(30)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        flow.set_homogeneous(True)
        for video in videos:
            flow.append(self.video_card(video))
        self.feed_container.append(flow)
        self.update_pagination()

    def wall_options_changed(self, *_):
        self.store.set("wall_newest", self.wall_order.get_selected() == 0)
        self.store.set("wall_hide_watched", self.hide_watched.get_active())
        self.show_videos(self.feed_videos)

    def video_card(self, video):
        card = box(spacing=8)
        card.add_css_class("card")
        card.set_size_request(VIDEO_CARD_WIDTH, -1)
        card.set_halign(Gtk.Align.START)
        card.set_valign(Gtk.Align.START)
        picture = VideoThumbnail()
        picture.add_css_class("thumbnail")
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_can_shrink(True)
        preview = Gtk.Overlay()
        preview.set_valign(Gtk.Align.START)
        preview.set_child(picture)
        preview.set_overflow(Gtk.Overflow.HIDDEN)
        preview.add_css_class("preview")
        if video.id in self.watched_ids:
            watched = label("✓ Watched", "pill")
            watched.set_halign(Gtk.Align.START)
            watched.set_valign(Gtk.Align.END)
            watched.set_margin_start(8)
            watched.set_margin_bottom(8)
            watched.set_tooltip_text("Completed in QuietTube on this computer")
            preview.add_overlay(watched)
        card.append(preview)
        if not self.demo:
            def loaded(data):
                try:
                    texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                    picture.set_paintable(texture)
                except GLib.Error:
                    pass
            self.thumbnails.load(video, loaded)
        title = label(video.title, "subheading", True)
        title.set_lines(2)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_max_width_chars(28)
        card.append(title)
        metadata = box(False, 6)
        channel = label(video.channel, "muted small")
        channel.set_ellipsize(Pango.EllipsizeMode.END)
        channel.set_max_width_chars(24)
        channel.set_hexpand(True)
        channel.set_tooltip_text(video.channel)
        metadata.append(channel)
        # Keep the age visible even when the channel name is very long.
        detail = label(" · ".join(filter(None, [duration_label(video.duration),
                                               published_label(video.published)])), "muted small")
        if video.published and published_label(video.published):
            detail.set_tooltip_text("Publish date from YouTube (feed dates may be approximate): " + video.published)
        metadata.append(detail)
        card.append(metadata)
        actions = box(spacing=6)
        actions.add_css_class("preview-actions")
        actions.set_halign(Gtk.Align.END)
        actions.set_valign(Gtk.Align.START)
        actions.set_margin_top(8)
        actions.set_margin_end(8)
        for icon, title, callback in [
            ("media-playback-start-symbolic", "Play or queue", lambda: self.play_video(video)),
            ("list-add-symbolic", "Add to queue", lambda: self.enqueue(video)),
            ("edit-copy-symbolic", "Copy YouTube link", lambda: self.copy_link(video)),
        ]:
            action = Gtk.Button(icon_name=icon, tooltip_text=title)
            action.update_property([Gtk.AccessibleProperty.LABEL], [title])
            action.connect("clicked", lambda _, callback=callback: callback())
            actions.append(action)
        like = Gtk.Button(icon_name="quiettube-like-symbolic")
        like.connect("clicked", lambda _: self.like_video(video))
        self.like_buttons.setdefault(video.id, []).append(like.weak_ref())
        self.update_like_button(like, video.id)
        actions.append(like)
        menu = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="More video actions")
        menu.set_always_show_arrow(False)
        menu.update_property([Gtk.AccessibleProperty.LABEL], ["More video actions"])
        popover = Gtk.Popover()
        items = box(spacing=5)
        popover_ref = popover.weak_ref()
        def perform(action):
            target = popover_ref()
            if target:
                target.popdown()
            action()
        items.append(button("Play next", lambda: perform(lambda: self.enqueue(video, 0))))
        items.append(button("Insert before selected", lambda: perform(lambda: self.insert_selected(video))))
        items.append(button("Find similar videos", lambda: perform(lambda: self.find_similar(video))))
        items.append(button("Copy YouTube link", lambda: perform(lambda: self.copy_link(video))))
        popover.set_child(items)
        menu.set_popover(popover)
        actions.append(menu)
        preview.add_overlay(actions)
        return card

    def update_pagination(self):
        hidden = len(self.feed_videos) - len(self.videos)
        suffix = f" · {hidden} watched hidden" if hidden else ""
        self.page_label.set_text(f"Page {self.page + 1} · {len(self.videos)} videos{suffix}" if self.feed_videos else "")
        self.previous_button.set_sensitive(not self.busy and self.page > 0)
        self.next_button.set_sensitive(not self.busy and self.has_more)

    def load_feed(self, kind):
        if self.pending in ACCOUNT_OPERATIONS and self.busy:
            self.set_status("Finish or cancel the account connection first.")
            return
        self.tasks.cancel()
        self.set_busy(False)
        self.feed, self.page = kind, 0
        self.page_tokens = {0: ""}
        self.query = ""
        titles = {"home": "Your home feed", "subscriptions": "Latest from your subscriptions",
                  "later": "Your Watch Later", "liked": "Your liked videos", "history": "Recently watched here"}
        self.feed_title.set_text(titles.get(kind, "Videos"))
        self.feed_caption.set_text("Your YouTube account feed." if kind != "history" else "History saved on this computer.")
        if self.oauth_mode() and kind in {"home", "subscriptions"}:
            self.feed_title.set_text("Recent subscription uploads")
            self.feed_caption.set_text("Personal OAuth · newest uploads, not YouTube Home recommendations.")
        for key, nav in self.nav.items():
            nav.remove_css_class("active")
            if key == kind:
                nav.add_css_class("active")
        if self.demo:
            self.has_more = False
            self.show_videos(DEMO_VIDEOS)
        elif kind == "history":
            self.has_more = False
            self.show_videos(self.store.history())
        elif not self.account_available():
            message = ("Sign in with Google using your saved personal Desktop client." if self.oauth_mode() else
                       "Connect a browser session to try QuietTube, or configure personal OAuth in Connect YouTube.")
            self.show_empty("Connect your YouTube account", message)
        else:
            self.request_feed()

    def oauth_mode(self):
        return self.store.get("account_mode", "browser") == "oauth"

    def account_available(self):
        return bool(self.store.get("oauth_authorized", False)) if self.oauth_mode() else self.store.cookie_path.exists()

    def account_request(self):
        if self.oauth_mode():
            return {"account_mode": "oauth", "account_dir": str(self.store.directory)}
        return {"session": str(self.store.cookie_path)}

    def request_feed(self, open_video=False, refresh=False):
        if self.pending in ACCOUNT_OPERATIONS:
            return
        self.pending = "open_video" if open_video else "feed"
        self.set_busy(True)
        self.set_status("Loading from YouTube…")
        self.tasks.submit({"kind": self.feed, "query": self.query, "page": self.page,
                           "page_token": self.page_tokens.get(self.page, ""), "refresh": refresh,
                           **self.account_request()})

    def reload(self):
        if self.demo or self.feed == "history":
            self.load_feed(self.feed)
        else:
            self.page = 0
            self.page_tokens = {0: ""}
            self.request_feed(refresh=True)

    def change_page(self, direction):
        self.page = max(0, self.page + direction)
        self.request_feed()

    def search(self):
        query = self.search_entry.get_text().strip()
        if not query:
            return
        if self.pending in ACCOUNT_OPERATIONS and self.busy:
            self.set_status("Finish or cancel the account connection first.")
            return
        if self.demo:
            self.show_videos([video for video in DEMO_VIDEOS if query.lower() in video.title.lower()])
            return
        self.page, self.query = 0, query
        self.page_tokens = {0: ""}
        if "://" in query:
            try:
                self.query = video_id(query)
                self.feed = "video"
            except ValueError:
                try:
                    self.query = playlist_url(query)
                    self.feed = "playlist"
                except ValueError as error:
                    self.set_status(str(error), True)
                    return
        else:
            self.feed = "search"
        for nav in self.nav.values():
            nav.remove_css_class("active")
        self.feed_title.set_text("Search results" if self.feed == "search" else "From your link")
        self.feed_caption.set_text(query[:120])
        self.request_feed(open_video=self.feed == "video")

    def find_similar(self, video):
        self.search_entry.set_text(video.title[:120])
        self.search()
        self.feed_title.set_text("Similar topics")
        self.feed_caption.set_text("Search-based suggestions; these are not YouTube's personalised next-video recommendations.")

    def cancel_request(self):
        self.tasks.cancel()
        self.pending = ""
        self.set_busy(False)
        self.set_status("Request cancelled.")

    def on_result(self, result):
        if self.closed or result.generation != self.tasks.generation:
            return False
        operation, self.pending = self.pending, ""
        self.set_busy(False)
        if result.error:
            self.set_status(result.error, True)
            if operation in ACCOUNT_OPERATIONS and self.account_window:
                self.account_message(result.error)
            if self.oauth_mode():
                code = (result.data or {}).get("code")
                if code == "unsupported":
                    self.show_empty("Unavailable with personal OAuth", result.error)
                else:
                    self.oauth_verified = False
                if code in {"sign_in_required", "client_not_configured"}:
                    self.store.set("oauth_authorized", False)
                    self.show_empty("Google sign-in needed", "Open Connect YouTube → Personal OAuth to sign in again.")
                self.refresh_transport()
            return False
        data = result.data or {}
        if operation == "oauth_configure":
            self.store.set("oauth_configured", True)
            self.store.set("oauth_authorized", data.get("authorization_saved", False))
            if data.get("client_changed"):
                self.oauth_verified = False
                if self.oauth_mode():
                    self.show_empty("Desktop client saved", "Sign in with Google to use this configuration.")
            self.account_message("Desktop client saved in the keyring. Choose Sign in with Google when ready.")
            self.set_status("Personal Desktop client saved. Your active connection method has not changed.")
            self.refresh_transport()
            return False
        if operation == "oauth_forget":
            self.history_sync.reset()
            self.store.set("oauth_configured", False)
            self.store.set("oauth_authorized", False)
            self.oauth_verified = False
            if self.oauth_mode():
                self.controller.stop()
                self.show_empty("Personal OAuth removed", "Sign in again or explicitly connect a browser session.")
            self.account_message("Personal OAuth removed from the keyring. You can also revoke access on Google's permissions page.")
            self.set_status("Personal OAuth removed; local queue and history retained.")
            self.refresh_transport()
            return False
        if operation == "oauth_connect":
            self.history_sync.reset()
            self.controller.stop()
            self.store.set("account_mode", "oauth")
            self.store.set("oauth_authorized", True)
            self.store.set("oauth_configured", True)
            self.oauth_verified = True
            self.liked_ids.clear()
            if self.account_window:
                self.account_window.close()
            self.refresh_transport()
            self.load_feed("home")
            return False
        if operation == "connect":
            self.history_sync.reset()
            self.controller.stop()
            self.store.set("account_mode", "browser")
            self.oauth_verified = False
            self.liked_ids.clear()
            self.store.set("account_source", self.account_source)
            self.account_button.set_label("YouTube connected")
            if self.account_window:
                self.account_window.close()
            self.set_status("YouTube connected. You can close the browser now.")
            self.load_feed("home")
            return False
        try:
            videos = [Video(**item) for item in data.get("videos", [])]
        except (TypeError, ValueError):
            self.set_status("Could not read these videos. Please retry.", True)
            return False
        self.has_more = data.get("has_more", False)
        if data.get("next_page_token"):
            self.page_tokens[self.page + 1] = data["next_page_token"]
        if self.oauth_mode() and data.get("account_connected"):
            self.oauth_verified = True
            self.refresh_transport()
        self.show_videos(videos)
        if data.get("note"):
            self.feed_caption.set_text(data["note"])
        self.set_status(f"Showing {len(self.videos)} of {len(videos)} loaded videos. Add anything you like to your queue.")
        if operation == "open_video" and videos:
            self.play_video(videos[0])
        return False

    def copy_link(self, video):
        self.get_clipboard().set(video.url)
        self.set_status("YouTube link copied to the clipboard.")

    def paste_link(self):
        def received(clipboard, result):
            if self.closed:
                return
            try:
                value = clipboard.read_text_finish(result) or ""
                ident = video_id(value)
            except (GLib.Error, ValueError):
                self.set_status("Copy a YouTube video link first, then choose Paste link.", True)
                return
            self.search_entry.set_text(f"https://www.youtube.com/watch?v={ident}")
            self.search()
        self.get_clipboard().read_text_async(None, received)

    def update_like_button(self, button, ident):
        liked = ident in self.liked_ids
        title = "Liked on YouTube" if liked else "Like on YouTube"
        if self.like_pending == ident:
            title = "Waiting for YouTube to confirm…"
        button.set_tooltip_text(title)
        button.update_property([Gtk.AccessibleProperty.LABEL], [title])
        button.set_sensitive(not liked and self.like_pending is None)
        if liked:
            button.add_css_class("liked")
        else:
            button.remove_css_class("liked")

    def refresh_like_buttons(self):
        for ident, references in self.like_buttons.items():
            for reference in references:
                target = reference()
                if target:
                    self.update_like_button(target, ident)

    def like_video(self, video):
        if self.demo:
            self.set_status("Likes are disabled in preview mode.")
            return
        if self.pending in ACCOUNT_OPERATIONS:
            self.set_status("Finish or cancel the account change before liking a video.")
            return
        if self.like_pending:
            self.set_status("Wait for YouTube to confirm the current Like request.")
            return
        if not self.account_available():
            self.set_status("Connect your YouTube account before liking a video.", True)
            self.open_account()
            return
        if video.id in self.liked_ids:
            return
        self.like_pending = video.id
        self.refresh_like_buttons()
        self.set_status("Sending Like to YouTube…")
        self.rating_tasks.submit({"action": "like", "video_id": video.id, **self.account_request()})

    def on_like_result(self, result):
        if self.closed or result.generation != self.rating_tasks.generation:
            return False
        ident, self.like_pending = self.like_pending, None
        data = result.data or {}
        if result.error:
            self.set_status(result.error + " Like was not confirmed.", True)
            if self.oauth_mode() and data.get("code") in {"sign_in_required", "client_not_configured"}:
                self.oauth_verified = False
                self.store.set("oauth_authorized", False)
                self.refresh_transport()
        elif ident and data.get("liked") is True and data.get("video_id") == ident:
            if any(video.id == ident for video in self.videos):
                self.liked_ids.add(ident)
            self.set_status("Liked on YouTube. It will appear in your Liked videos.")
        else:
            self.set_status("YouTube did not confirm the Like. Check Liked videos before retrying.", True)
        self.refresh_like_buttons()
        return False

    def enqueue(self, video, index=None):
        try:
            self.controller.add(video, index)
            self.set_status(f"Added to queue: {video.title}")
        except ValueError as error:
            self.set_status(str(error), True)

    def selected_index(self):
        row = self.queue_list.get_selected_row()
        return row.get_index() if row else None

    def insert_selected(self, video):
        index = self.selected_index()
        if index is None:
            self.set_status("Select a queued video first, then choose Insert before selected.")
        else:
            self.enqueue(video, index)

    def queue_selected(self, _, row):
        self.last_selected = getattr(row, "item_key", None) if row else None
        if row:
            self.move_position.set_value(row.get_index() + 1)

    def move_selected(self, delta):
        index = self.selected_index()
        if index is not None:
            self.controller.move(self.controller.queue.upcoming[index].key, index + delta)

    def move_to_position(self):
        index = self.selected_index()
        if index is not None:
            self.controller.move(self.controller.queue.upcoming[index].key, self.move_position.get_value_as_int() - 1)

    def remove_selected(self):
        index = self.selected_index()
        if index is not None:
            self.controller.remove(self.controller.queue.upcoming[index].key)

    def play_video(self, video):
        if self.demo:
            self.set_status("Playback is disabled in preview mode. Launch normally to watch YouTube.")
            return
        if self.controller.queue.current or self.controller.queue.upcoming:
            if self.play_choice:
                self.play_choice.present()
                return
            dialog = Gtk.Window(title="Play or queue?", transient_for=self, modal=True)
            self.play_choice = dialog
            dialog.set_default_size(460, 210)
            content = box(spacing=14)
            for setter in (content.set_margin_start, content.set_margin_end, content.set_margin_top, content.set_margin_bottom):
                setter(24)
            content.append(label("Play now or save it for later?", "subheading"))
            video_label = label(video.title, wrap=True)
            video_label.set_max_width_chars(44)
            video_label.set_lines(3)
            video_label.set_ellipsize(Pango.EllipsizeMode.END)
            content.append(video_label)
            content.append(label("Add to queue keeps your current video playing. Play now saves it to resume later.", "muted", True))
            choices = box(False)
            choices.append(button("Cancel", lambda: self.finish_play_choice("cancel", video)))
            choices.append(button("Play now", lambda: self.finish_play_choice("play", video)))
            choices.append(button("Add to queue", lambda: self.finish_play_choice("queue", video), "suggested-action"))
            content.append(choices)
            dialog.set_child(content)
            dialog.connect("close-request", self.play_choice_closed)
            dialog.present()
            return
        self.start_video(video)

    def play_choice_closed(self, *_):
        self.play_choice = None
        return False

    def finish_play_choice(self, choice, video):
        if self.play_choice:
            self.play_choice.close()
        if choice == "play":
            self.start_video(video)
        elif choice == "queue":
            self.enqueue(video)

    def start_video(self, video):
        try:
            self.controller.play_now(video)
        except ValueError as error:
            self.set_status(str(error), True)

    def play(self):
        if self.demo:
            self.set_status("Playback is disabled in preview mode. Launch normally to watch YouTube.")
        elif self.controller.state == "error":
            self.open_playback_help()
        else:
            self.controller.play()

    def reload_video(self):
        if not self.demo and self.controller.queue.current:
            self.controller.reload()
            self.set_status("Reloading fresh video and audio streams at your saved position…")

    def skip(self):
        if not self.demo:
            self.controller.next()

    def on_player(self, event):
        if not self.closed:
            completed = (event.kind in {"finished", "dismissed"} and event.generation == self.player.generation
                         and self.controller.queue.current is not None)
            self.controller.event(event)
            if completed:
                self.show_videos(self.store.history() if self.feed == "history" else self.feed_videos)
        return False

    def refresh_transport(self):
        if self.closed:
            return
        queue = self.controller.queue
        current = queue.current
        self.now_title.set_text(current.video.title if current else "Pick your next video")
        if current:
            position = duration_label(current.position) or "0:00"
            duration = duration_label(self.controller.duration or current.video.duration) or "—"
            self.now_detail.set_text(f"{self.controller.state.capitalize()} · {position} / {duration} · {current.video.channel}")
        else:
            self.now_detail.set_text("Playback opens in a lightweight mpv window.")
        self.play_button.set_label({"playing": "Pause", "paused": "Resume", "loading": "Loading…"}.get(self.controller.state, "Play"))
        self.play_button.set_sensitive(self.controller.state != "loading")
        failed = self.controller.state == "error" and current is not None
        self.playback_help_button.set_visible(failed)
        self.skip_failed_button.set_visible(failed and bool(queue.upcoming))
        self.queue_play_button.set_label("Resolve failed video" if failed else "Play queue")
        if self.controller.error:
            self.set_status(self.controller.error, True)
        elif self.controller.state == "loading" and current:
            self.set_status(f"Opening: {current.video.title}")
        signature = tuple(item.key for item in queue.upcoming)
        if signature != self.queue_signature:
            selected = self.last_selected
            clear(self.queue_list)
            for index, item in enumerate(queue.upcoming):
                row = Gtk.ListBoxRow()
                row.item_key = item.key
                content = box(spacing=4)
                content.add_css_class("queue-row")
                title = label(f"{index + 1:02}  {item.video.title}", wrap=True)
                title.set_max_width_chars(28)
                title.set_lines(2)
                title.set_ellipsize(Pango.EllipsizeMode.END)
                content.append(title)
                content.append(label(item.video.channel[:35], "muted small"))
                row.set_child(content)
                self.queue_list.append(row)
                if item.key == selected:
                    self.queue_list.select_row(row)
            self.queue_signature = signature
            self.queue_title.set_text(f"Up next · {len(queue.upcoming)}")
        self.playback_connection_button.set_label(
            "Playback session · saved" if self.store.get("playback_session_enabled", False) and self.store.playback_cookie_path.exists()
            else "Connect playback")
        if self.oauth_mode():
            state = "connected" if self.oauth_verified else ("saved" if self.account_available() else "sign in needed")
            self.account_button.set_label("Personal OAuth · " + state)
            self.account_button.set_tooltip_text("Account feed connection. OAuth does not authenticate mpv playback. Click for Google sign-in and settings.")
        else:
            self.account_button.set_label("YouTube connected" if self.store.cookie_path.exists() else "Connect YouTube")
            self.account_button.set_tooltip_text("Connect or manage the browser session")

    def open_playback_connection(self):
        if self.demo:
            return
        if self.playback_help_window:
            self.playback_help_window.close()
        if self.playback_connection_window:
            self.playback_connection_window.present()
            return
        from .playback_connection import PlaybackConnectionWindow
        def updated():
            self.history_sync.reset()
            if self.oauth_mode():
                self.controller.stop()
            self.refresh_transport()
            self.set_status("Playback connection updated. Press Play to retry at the saved position; account feeds are unchanged.")
        def closed(*_):
            self.playback_connection_window = None
        self.playback_connection_window = PlaybackConnectionWindow(self, self.store, updated, self.history_sharing_changed)
        self.playback_connection_window.connect("close-request", closed)
        self.playback_connection_window.present()

    def open_playback_help(self):
        item = self.controller.queue.current
        if self.demo or not item:
            return
        if self.playback_help_window:
            self.playback_help_window.present()
            return
        dialog = Gtk.Window(title="Playback help", transient_for=self, modal=True)
        dialog.set_default_size(560, 640)
        self.playback_help_window = dialog
        def closed(*_):
            self.playback_help_window = None
            return False
        dialog.connect("close-request", closed)
        content = box(spacing=14)
        for setter in (content.set_margin_start, content.set_margin_end, content.set_margin_top, content.set_margin_bottom):
            setter(24)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(content)
        dialog.set_child(scroll)
        content.append(label("Playback recovery", "subheading", True))
        content.append(label(item.video.title, "subheading", True))
        content.append(label(self.controller.error or "Playback could not start.", "small", True))
        content.append(label("If other videos play, this item may be unavailable. A failed live stream or an old "
                             "resume point can block the queue. Choose how to continue.", "small", True))
        def recover(action):
            dialog.close()
            # The queue may have changed while this dialog was open.
            if not self.controller.queue.current or self.controller.queue.current.key != item.key:
                return
            action()
        self.retry_saved_button = button("Retry at saved position", lambda: recover(self.controller.reload))
        content.append(self.retry_saved_button)
        self.restart_failed_button = button("Start from beginning / live edge", lambda: recover(self.controller.restart_current))
        content.append(self.restart_failed_button)
        self.skip_help_button = button("Skip this video and play next", lambda: recover(self.skip), "suggested-action")
        self.skip_help_button.set_sensitive(bool(self.controller.queue.upcoming))
        content.append(self.skip_help_button)
        content.append(label("Skipping removes this item from the queue without marking it fully watched.", "muted small", True))
        content.append(label("Playback and account access are separate", "subheading", True))
        if self.oauth_mode():
            explanation = ("Personal OAuth connects your dashboard, subscriptions and Likes. It does not sign mpv into "
                           "YouTube's video service. The connected badge describes account data only. Signing in with "
                           "Google again will not fix a playback verification challenge. Connect playback to explicitly save a separate browser session for mpv.")
        else:
            explanation = ("Playback uses your imported YouTube website session when one is saved. That session can expire, "
                           "and YouTube can still require browser verification. Reconnecting it is not a guaranteed fix.")
        content.append(label(explanation, "muted", True))
        content.append(button("Connect / reconnect playback", self.open_playback_connection, "suggested-action"))
        content.append(label("Wait before retrying if YouTube asks for verification or limits requests. You can open this "
                             "video on YouTube at the saved position. Browser playback will not advance QuietTube's queue "
                             "or update its saved position.", "small", True))
        url = item.video.url + "&t=" + str(int(finite_seconds(item.position))) + "s"
        def open_video():
            try:
                Gio.AppInfo.launch_default_for_uri(url, None)
            except GLib.Error:
                self.set_status("Could not open the browser. Use Copy video link instead.", True)
        self.playback_browser_button = button("Open this video on YouTube", open_video, "suggested-action")
        content.append(self.playback_browser_button)
        content.append(button("Copy video link", lambda: self.copy_link(item.video)))
        content.append(button("Close", dialog.close))
        dialog.present()

    def quality_changed(self, *_):
        self.controller.height = [480, 720, 1080, 1440, 2160][self.quality.get_selected()]
        self.store.set("quality", self.controller.height)
        self.set_status("Quality limit saved. It applies when the next video starts.")

    def volume_changed(self, *_):
        self.controller.volume = self.volume.get_value()
        self.player.command(["set_property", "volume", self.controller.volume])
        self.store.set("volume", self.controller.volume)

    def open_account(self):
        if self.demo:
            self.set_status("Account access is disabled in preview mode. Launch normally to connect YouTube.")
            return
        if self.account_window:
            self.account_window.present()
            return
        dialog = Gtk.Window(title="Connect YouTube", transient_for=self, modal=True)
        dialog.set_default_size(680, 760)
        self.account_window = dialog
        dialog.connect("close-request", self.account_closed)
        content = box(spacing=14)
        for setter in (content.set_margin_start, content.set_margin_end, content.set_margin_top, content.set_margin_bottom):
            setter(24)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(content)
        dialog.set_child(scroll)
        content.append(label("Connect your YouTube", "heading"))
        content.append(label("Start with a browser session, or configure your own Desktop OAuth client below.", "muted", True))
        self.oauth_sign_in_shortcut = None
        if self.oauth_mode():
            content.append(label("OAuth is selected for account feeds. Google sign-in here does not authenticate mpv playback.", "small", True))
            self.oauth_sign_in_shortcut = button("Sign in with Google for account feeds", lambda: self.oauth_request("oauth_connect"))
            content.append(self.oauth_sign_in_shortcut)
        content.append(label("Sign in on YouTube in your browser, then connect that browser's session. "
                             "Your password stays with Google. You can close the browser afterward.", "muted", True))
        content.append(button("1. Open YouTube sign-in", lambda: Gio.AppInfo.launch_default_for_uri(
            "https://www.youtube.com/feed/subscriptions", None)))
        content.append(label("2. Choose the browser you signed in with", "subheading"))
        self.browser_names = ["chromium", "chrome", "brave", "edge", "firefox", "vivaldi", "opera"]
        self.browser = Gtk.DropDown.new_from_strings(["Chromium", "Google Chrome", "Brave", "Microsoft Edge", "Firefox", "Vivaldi", "Opera"])
        saved = self.store.get("account_source", {})
        if saved.get("browser") in self.browser_names:
            self.browser.set_selected(self.browser_names.index(saved["browser"]))
        content.append(self.browser)
        self.profile = Gtk.Entry(placeholder_text="Optional browser profile name or full path")
        def profile_hint(*_):
            browser = self.browser_names[self.browser.get_selected()]
            profile = saved.get("profile", "") if saved.get("browser") == browser else ""
            self.profile.set_text(profile or suggested_profile(browser))
        profile_hint()
        self.browser.connect("notify::selected", profile_hint)
        content.append(self.profile)
        content.append(label("QuietTube reads the selected browser's cookies to find your session and keeps only "
                             "youtube.com cookies in a local file readable by your OS user. It does not upload them "
                             "to a third-party service. Reconnect here if YouTube expires the session.", "muted small", True))
        self.account_actions = box(spacing=8)
        self.account_actions.append(button("3. Connect browser session", self.connect_browser, "suggested-action"))
        self.account_actions.append(button("Import a YouTube cookies.txt file instead", self.choose_cookies))
        if self.store.cookie_path.exists():
            self.account_actions.append(button("Remove saved browser session", self.disconnect))
        content.append(self.account_actions)
        self.account_progress = label("", "small", True)
        content.append(self.account_progress)
        content.append(label("Uses unofficial YouTube access. YouTube can restrict it or require a fresh login. "
                             "The queue is local; it does not modify your YouTube playlists.", "muted small", True))
        self.build_oauth_setup(content)
        self.set_busy(self.busy)
        dialog.present()

    def build_oauth_setup(self, content):
        from .oauth_help import SETUP_STEPS, SCOPES_TEXT, STORAGE_TEXT, LIMITS_TEXT
        self.oauth_expander = Gtk.Expander(label="Personal OAuth · experimental")
        self.oauth_expander.set_expanded(self.oauth_mode())
        content.append(self.oauth_expander)
        panel = box(spacing=14)
        self.oauth_expander.set_child(panel)
        panel.append(label("Your project, your connection", "subheading"))
        panel.append(label(LIMITS_TEXT, "muted small", True))
        for title, url, instructions in SETUP_STEPS:
            if url:
                link = Gtk.LinkButton.new_with_label(url, title)
                link.set_halign(Gtk.Align.START)
                panel.append(link)
            else:
                panel.append(label(title, "subheading"))
            panel.append(label(instructions, "small", True))
            if title.startswith("5."):
                scope = Gtk.Entry(text=SCOPES_TEXT, editable=False)
                scope.set_tooltip_text("Select and copy this scope into Google's Data Access screen")
                panel.append(scope)
        panel.append(label(STORAGE_TEXT, "muted small", True))
        self.oauth_actions = box(spacing=8)
        panel.append(self.oauth_actions)
        self.oauth_actions.append(button("Import Desktop JSON", self.choose_oauth_client, "suggested-action"))
        self.oauth_actions.append(label("Or paste the two values from your Desktop client:", "small", True))
        self.oauth_actions.append(label("Client ID", "small"))
        self.oauth_client_id = Gtk.Entry(placeholder_text="…apps.googleusercontent.com", max_length=256)
        self.oauth_actions.append(self.oauth_client_id)
        self.oauth_actions.append(label("Client secret", "small"))
        self.oauth_client_secret = Gtk.Entry(placeholder_text="Desktop OAuth client secret", visibility=False,
                                             input_purpose=Gtk.InputPurpose.PASSWORD, max_length=512)
        self.oauth_actions.append(self.oauth_client_secret)
        self.oauth_actions.append(button("Save to keyring", self.save_oauth_client))
        self.oauth_actions.append(button("Sign in with Google", lambda: self.oauth_request("oauth_connect"), "suggested-action"))
        self.oauth_actions.append(button("Remove personal OAuth from keyring", lambda: self.oauth_request("oauth_forget")))
        message = ("A Desktop configuration was saved here. Sign in to verify it." if self.store.get("oauth_configured")
                   else "Import or save your Desktop client, then sign in. Saving alone does not change your connection.")
        self.oauth_progress = label(message, "small", True)
        panel.append(self.oauth_progress)
        panel.append(Gtk.LinkButton.new_with_label("https://myaccount.google.com/connections", "Review or revoke access on Google"))

    def account_message(self, text):
        if self.account_window:
            self.account_progress.set_text(text)
            self.oauth_progress.set_text(text)

    def oauth_request(self, action, **fields):
        if self.demo or not self.account_window:
            return
        if self.like_pending:
            self.account_message("Wait for the current Like request to finish before changing account configuration.")
            return
        self.tasks.cancel()
        self.pending = action
        self.set_busy(True)
        message = ("Complete sign-in in your default browser. Close this dialog to cancel."
                   if action == "oauth_connect" else "Accessing your desktop keyring…")
        self.account_message(message)
        self.set_status(message)
        self.tasks.submit({"action": action, "account_dir": str(self.store.directory), **fields})

    def save_oauth_client(self):
        ident = self.oauth_client_id.get_text().strip()
        secret = self.oauth_client_secret.get_text().strip()
        self.oauth_client_id.set_text("")
        self.oauth_client_secret.set_text("")
        self.oauth_request("oauth_configure", client_id=ident, client_secret=secret)

    def choose_oauth_client(self):
        chooser = Gtk.FileChooserNative(title="Import your Google Desktop client JSON", transient_for=self.account_window,
                                         action=Gtk.FileChooserAction.OPEN, accept_label="Import", cancel_label="Cancel")
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Google Desktop OAuth JSON")
        file_filter.add_pattern("*.json")
        chooser.add_filter(file_filter)
        def response(dialog, result):
            if result == Gtk.ResponseType.ACCEPT and self.account_window and not self.closed:
                file = dialog.get_file()
                path = file.get_path() if file else None
                if path:
                    self.oauth_request("oauth_configure", client_file=path)
            dialog.destroy()
        chooser.connect("response", response)
        chooser.show()

    def account_closed(self, *_):
        if self.pending in ACCOUNT_OPERATIONS:
            self.cancel_request()
        self.oauth_client_id.set_text("")
        self.oauth_client_secret.set_text("")
        self.account_window = None
        return False

    def connect_browser(self):
        self.account_source = {"browser": self.browser_names[self.browser.get_selected()],
                               "profile": self.profile.get_text().strip()}
        self.connect_session(self.account_source)

    def connect_session(self, source):
        if self.like_pending:
            self.account_progress.set_text("Wait for the current Like request to finish before reconnecting.")
            return
        self.pending = "connect"
        self.set_busy(True)
        self.account_progress.set_text("Connecting and checking your subscription feed…")
        self.set_status("Checking the selected YouTube session…")
        self.tasks.submit({"action": "connect", "session": str(self.store.cookie_path), **source})

    def choose_cookies(self):
        chooser = Gtk.FileChooserNative(title="Choose exported YouTube cookies", transient_for=self.account_window,
                                         action=Gtk.FileChooserAction.OPEN, accept_label="Connect", cancel_label="Cancel")
        def response(dialog, result):
            if result == Gtk.ResponseType.ACCEPT and self.account_window:
                path = dialog.get_file().get_path()
                if path:
                    self.account_source = {"browser": "cookie-file"}
                    self.connect_session({"cookie_file": path})
            dialog.destroy()
        chooser.connect("response", response)
        chooser.show()

    def disconnect(self):
        self.history_sync.reset()
        self.tasks.cancel()
        self.rating_tasks.cancel()
        self.like_pending = None
        self.liked_ids.clear()
        self.controller.stop()
        self.store.cookie_path.unlink(missing_ok=True)
        self.store.set("account_source", {})
        self.thumbnails.close()
        self.thumbnails = Thumbnails(GLib.idle_add)
        if self.account_window:
            self.account_window.close()
        self.load_feed("home")
        self.refresh_transport()
        if self.oauth_mode():
            self.set_status("Browser session removed. Personal OAuth stays selected; use Remove personal OAuth to delete its keyring entry.")
        else:
            self.set_status("Disconnected. Saved session removed; your local queue and history are retained.")

    def checkpoint(self):
        if self.closed:
            return False
        self.controller.checkpoint()
        return True

    def on_close(self, *_):
        if not self.closed:
            self.closed = True
            if self.play_choice:
                self.play_choice.close()
            GLib.source_remove(self.checkpoint_timer)
            self.tasks.close()
            self.rating_tasks.close()
            if self.account_window:
                self.account_window.close()
            if self.playback_help_window:
                self.playback_help_window.close()
            if self.playback_connection_window:
                self.playback_connection_window.close()
            self.thumbnails.close()
            self.controller.close()
            self.history_sync.close()
            self.store.close()
        return False


class QuietTubeApp(Gtk.Application):
    def __init__(self, directory: Path, demo=False, quit_after=0):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.directory, self.demo, self.quit_after = directory, demo, quit_after
        self.window = None

    def do_activate(self):
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(
            str(Path(__file__).with_name("icons")))
        Gtk.Window.set_default_icon_name(APP_ID)
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", True)
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        if not self.window:
            self.window = MainWindow(self, self.directory, self.demo)
        self.window.present()
        if self.quit_after:
            GLib.timeout_add_seconds(self.quit_after, lambda: self.window.close() or False)
