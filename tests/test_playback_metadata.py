"""Exercise the pinned extractor CLI with synthetic, offline stream metadata."""
import json
import subprocess
import sys

from quiettube.player import mpv_command, PlaybackDiagnostics


def test_selected_dash_fragments_survive_compaction(tmp_path):
    formats = []
    for n in range(20):
        formats.append({
            'format_id': str(n), 'ext': 'mp4', 'protocol': 'http_dash_segments',
            'url': f'https://example.invalid/{n}.mp4', 'height': 144 + n * 100,
            'vcodec': 'h264', 'acodec': 'none',
            'fragments': [{'url': f'https://example.invalid/{n}/{i}.m4s', 'duration': 2} for i in range(100)],
        })
    formats.append({'format_id': 'audio', 'ext': 'm4a', 'protocol': 'http_dash_segments',
                    'url': 'https://example.invalid/audio.m4a', 'vcodec': 'none', 'acodec': 'aac',
                    'fragments': [{'url': 'https://example.invalid/audio.m4s', 'duration': 2}]})
    data = {'id': '11111111111', 'title': 'Synthetic ended stream', 'extractor': 'youtube',
            'webpage_url': 'https://www.youtube.com/watch?v=11111111111',
            'live_status': 'post_live', 'formats': formats}
    source = tmp_path/'info.json'
    source.write_text(json.dumps(data))
    args = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--load-info-json', str(source),
            '--dump-single-json', '--user-agent', 'SyntheticQuietTubeTest/1', '--format', 'bestvideo[height<=720]+bestaudio', '--no-warnings']
    before = subprocess.run(args, capture_output=True, text=True, check=True, timeout=20)
    options = next(arg.split('=', 1)[1] for arg in mpv_command('/tmp/synthetic.sock', 720)
                   if arg.startswith('--ytdl-raw-options='))
    pruning = next(option.split('=', 1)[1] for option in options.split(',') if option.startswith('parse-metadata='))
    after = subprocess.run(args + ['--parse-metadata', pruning], capture_output=True,
                           text=True, check=True, timeout=20)
    original, compact = json.loads(before.stdout), json.loads(after.stdout)
    assert not compact.get('formats')
    assert compact['requested_formats'] == original['requested_formats']
    assert compact['title'] == original['title']
    assert compact['live_status'] == 'post_live'
    assert len(after.stdout) < len(before.stdout) / 3


def test_metadata_error_is_distinct_from_account_and_does_not_log_raw_data(tmp_path):
    from quiettube.diagnostics import PlaybackLog
    diagnostic = PlaybackDiagnostics()
    assert diagnostic.observe('youtube-dl failed: failed to parse JSON data: error') == 'metadata'
    assert 'metadata' in diagnostic.error()
    log = PlaybackLog(tmp_path)
    log.write('error', 1, category=diagnostic.category, url='https://private.invalid/secret')
    assert json.loads(log.path.read_text())['category'] == 'metadata'
    assert 'secret' not in log.path.read_text()
    diagnostic.observe("Sign in to confirm you're not a bot")
    diagnostic.observe('failed to parse JSON data')
    assert diagnostic.category == 'verification'


def test_unopenable_media_is_not_misreported_as_account_failure():
    diagnostic = PlaybackDiagnostics()
    diagnostic.observe("EDL: Could not open source file 'https://example.invalid/private'")
    assert diagnostic.category == 'stream'
    assert 'skip' in diagnostic.error()
    assert 'private' not in diagnostic.error()
