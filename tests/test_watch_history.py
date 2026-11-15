from urllib.parse import parse_qs, urlsplit

import pytest

from quiettube.watch_history import HistoryError, report_position, share_position, tracking_url

IDENT = 'jNQXAC9IVRw'


class Client:
    def __init__(self):
        self.sent = []
        self.player = {'videoDetails': {'videoId': IDENT, 'lengthSeconds': '600'}, 'playbackTracking': {
            'videostatsPlaybackUrl': {'baseUrl': 'https://s.youtube.com/api/stats/playback?token=SECRET'},
            'videostatsWatchtimeUrl': {'baseUrl': 'https://s.youtube.com/api/stats/watchtime?token=SECRET'}}}

    def watch_page(self, ident):
        assert ident == IDENT
        return self.player, ''

    def send(self, url):
        self.sent.append(url)


def test_progress_reports_actual_position_without_inventing_full_watch():
    client = Client()
    result = report_position(client, IDENT, 123.4567)
    assert result == {'history_sent': True, 'video_id': IDENT, 'position': 123.457}
    assert len(client.sent) == 2
    queries = [parse_qs(urlsplit(url).query) for url in client.sent]
    assert queries[0]['cpn'] == queries[1]['cpn']
    assert queries[1]['st'] == queries[1]['et'] == queries[1]['cmt'] == ['123.457']
    assert queries[1]['final'] == ['1']
    assert all(urlsplit(url).hostname == 'www.youtube.com' for url in client.sent)
    assert 'SECRET' not in str(result)
    assert '600' not in str(queries)


@pytest.mark.parametrize('position', [0, -1, float('nan'), float('inf'), '123', True, 700000])
def test_invalid_position_never_sends(position):
    client = Client()
    with pytest.raises(HistoryError):
        report_position(client, IDENT, position)
    assert not client.sent


@pytest.mark.parametrize('url', ['https://evil.test/api/stats/watchtime',
                                'https://www.youtube.com@evil.test/api/stats/watchtime',
                                'https://www.youtube.com:444/api/stats/watchtime',
                                'http://www.youtube.com/api/stats/watchtime',
                                'https://www.youtube.com/api/like'])
def test_endpoint_must_be_youtube_watchtime(url):
    with pytest.raises(HistoryError):
        tracking_url(url, 'watchtime', 123, 'nonce')


def test_missing_tracking_and_bad_duration_do_not_partially_send():
    client = Client()
    del client.player['playbackTracking']['videostatsWatchtimeUrl']
    with pytest.raises(HistoryError):
        report_position(client, IDENT, 123)
    assert not client.sent
    client = Client()
    with pytest.raises(HistoryError):
        report_position(client, IDENT, 900)
    assert not client.sent


def test_errors_and_cookie_content_never_escape_worker(tmp_path, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def broken(*_):
        raise RuntimeError('https://SECRET?cookie=PRIVATE')
        yield
    monkeypatch.setattr('quiettube.watch_history.history_client', broken)
    with pytest.raises(HistoryError) as error:
        share_position(IDENT, 20, tmp_path/'session', None)
    assert 'SECRET' not in str(error.value) and 'PRIVATE' not in str(error.value)


def test_worker_shares_with_disposable_cookie_copy(tmp_path, monkeypatch):
    from quiettube import worker
    session = tmp_path/'session'
    session.write_text('synthetic')
    snapshots = []
    def share(ident, position, path, logger):
        assert ident == IDENT and position == 20
        assert path != session and path.read_text() == 'synthetic'
        snapshots.append(path)
        path.write_text('worker-only mutation')
        return {'history_sent': True, 'video_id': ident, 'position': position}
    monkeypatch.setattr('quiettube.watch_history.share_position', share)
    assert worker.execute({'action':'history_sync', 'video_id': IDENT, 'position':20,
                           'session':str(session)})['history_sent']
    assert session.read_text() == 'synthetic'
    assert not snapshots[0].exists()


def test_client_checks_signed_in_video_and_live_status_before_sending():
    from quiettube.watch_history import HistoryClient
    class Extractor:
        config = {'LOGGED_IN': True}
        player = {'videoDetails': {'videoId': IDENT, 'lengthSeconds': '600'}}
        def extract_ytcfg(self, *args): return self.config
        def _search_json(self, *args, **kwargs): return self.player
    extractor = Extractor()
    client = HistoryClient(None, extractor)
    client.read = lambda url: 'synthetic page'
    assert client.watch_page(IDENT)[0] == extractor.player
    extractor.config = {'LOGGED_IN': False}
    with pytest.raises(HistoryError, match='Reconnect'):
        client.watch_page(IDENT)
    extractor.config = {'LOGGED_IN': True}
    extractor.player = {'videoDetails': {'videoId':'other'}}
    with pytest.raises(HistoryError, match='requested video'):
        client.watch_page(IDENT)
    extractor.player = {'videoDetails': {'videoId':IDENT, 'isLive':True}}
    with pytest.raises(HistoryError, match='live videos'):
        client.watch_page(IDENT)


def test_bounded_reads_and_http_failure():
    from quiettube.watch_history import HistoryClient, MAX_RESPONSE
    class Response:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit <= MAX_RESPONSE + 1
            return b'x' * limit
    class Downloader:
        def urlopen(self, url): return response
    response = Response()
    client = HistoryClient(Downloader(), None)
    with pytest.raises(HistoryError, match='too much'):
        client.read('synthetic')
    client.send('synthetic')
    response.status = 403
    with pytest.raises(HistoryError, match='not accept'):
        client.send('synthetic')
