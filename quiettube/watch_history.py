"""Unofficial YouTube history/progress reporting, isolated in a short-lived worker.

Position reporting follows YouTube.js MediaInfo.updateWatchTime. Unlike yt-dlp's
mark-watched option, st/et/cmt are the actual position, never the video length.
No watch time is invented for skipped ranges. HTTP acceptance is not evidence
that another device has received a resume point.
"""
from contextlib import contextmanager
import math
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .models import video_id

MAX_RESPONSE = 4 * 1024 * 1024


class HistoryError(Exception):
    """Only fixed, safe messages may cross the worker boundary."""


def position_seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 7 * 86400:
        raise HistoryError("No valid playback position to share.")
    return round(value, 3)


def tracking_url(url, kind, position, nonce):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in {'www.youtube.com', 's.youtube.com', 'youtube.com'}
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path != '/api/stats/' + kind):
        raise HistoryError("YouTube did not provide a supported history endpoint.")
    query = parse_qs(parsed.query)
    query.update(ver=['2'], cpn=[nonce], cmt=[str(position)], el=['detailpage'])
    if kind == 'watchtime':
        query.update(st=[str(position)], et=[str(position)], final=['1'])
    # YouTube.js uses the www host so authenticated website cookies apply.
    return urlunsplit(('https', 'www.youtube.com', parsed.path, urlencode(query, doseq=True), ''))


class HistoryClient:
    def __init__(self, downloader, extractor):
        self.downloader, self.extractor = downloader, extractor

    def read(self, url):
        with self.downloader.urlopen(url) as response:
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise HistoryError("YouTube returned too much history data.")
            return data.decode('utf-8', errors='replace')

    def watch_page(self, ident):
        page = self.read('https://www.youtube.com/watch?v=' + ident)
        config = self.extractor.extract_ytcfg(ident, page)
        if config.get('LOGGED_IN') is not True:
            raise HistoryError("Reconnect the playback session to share history with YouTube.")
        player = self.extractor._search_json(
            r'ytInitialPlayerResponse\s*=', page, 'player response', ident, default={})
        if player.get('videoDetails', {}).get('videoId') != ident:
            raise HistoryError("YouTube did not confirm the requested video for history sharing.")
        if (player.get('videoDetails', {}).get('isLive')
                or player.get('microformat', {}).get('playerMicroformatRenderer', {})
                .get('liveBroadcastDetails', {}).get('isLiveNow')):
            raise HistoryError("History position sharing is unavailable for live videos.")
        return player, page

    def send(self, url):
        # Responses can be empty (204). Never expose their raw contents or URLs.
        with self.downloader.urlopen(url) as response:
            if not 200 <= response.status < 300:
                raise HistoryError("YouTube did not accept the history update.")
            response.read(1024)


def report_position(client, ident, position):
    ident, position = video_id(ident), position_seconds(position)
    player, _ = client.watch_page(ident)
    duration = float(player.get('videoDetails', {}).get('lengthSeconds') or 0)
    if not math.isfinite(duration) or duration <= 0 or position > duration + 2:
        raise HistoryError("The saved position does not match this video's duration.")
    position = min(position, duration)
    tracking = player.get('playbackTracking', {})
    nonce = secrets.token_urlsafe(12)
    urls = [tracking_url(tracking.get(key, {}).get('baseUrl', ''), kind, position, nonce)
            for key, kind in [('videostatsPlaybackUrl', 'playback'), ('videostatsWatchtimeUrl', 'watchtime')]]
    for url in urls:
        client.send(url)
    return {'history_sent': True, 'video_id': ident, 'position': position}


@contextmanager
def history_client(session: Path, logger):
    if not session or not session.is_file():
        raise HistoryError("Connect a playback session before sharing watch history.")
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeIE
    with YoutubeDL({'cookiefile': str(session), 'logger': logger, 'quiet': True,
                    'cachedir': False, 'socket_timeout': 8, 'retries': 0,
                    'extractor_retries': 0, 'mark_watched': False}) as downloader:
        extractor = YoutubeIE(downloader)
        extractor.initialize()
        yield HistoryClient(downloader, extractor)


def share_position(ident, position, session, logger):
    try:
        with history_client(session, logger) as client:
            return report_position(client, ident, position)
    except HistoryError:
        raise
    except Exception:
        raise HistoryError("Watch history could not be shared. Playback and local resume are unaffected.") from None
