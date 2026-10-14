"""Read this Codex thread's latest recorded usage; never modify Codex data."""
import json
import os
import sqlite3
from pathlib import Path


def reverse_lines(path, limit=2 * 1024 * 1024):
    with path.open('rb') as stream:
        end = stream.seek(0, 2)
        floor = max(0, end - limit)
        pending = b''
        while end > floor:
            start = max(floor, end - 65536)
            stream.seek(start)
            parts = (stream.read(end - start) + pending).split(b'\n')
            pending = parts[0]
            yield from reversed(parts[1:])
            end = start
        if floor == 0 and pending:
            yield pending


def latest_usage(path, thread_id):
    fallback = None
    for line in reverse_lines(path):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        payload = event.get('payload') or {}
        if event.get('type') == 'token_usage_record':
            if payload.get('thread_id') == thread_id:
                usage = payload.get('turn_token_usage')
                if usage:
                    return summarize(event, usage, 'current_turn_recorded', payload.get('turn_id'))
        if event.get('type') == 'event_msg':
            if payload.get('type') == 'task_started':
                break  # Never substitute a previous turn for the active turn.
            if payload.get('type') == 'token_count' and fallback is None:
                usage = (payload.get('info') or {}).get('last_token_usage')
                if usage:
                    fallback = summarize(event, usage, 'latest_request_recorded', None)
    return fallback or {'status': 'unavailable', 'reason': 'no current usage in bounded log tail'}


def summarize(event, usage, scope, turn_id):
    total = usage.get('input_tokens')
    cached = usage.get('cached_input_tokens')
    if not isinstance(total, int) or not isinstance(cached, int) or not 0 <= cached <= total:
        return {'status': 'unavailable', 'reason': 'invalid or missing token counts'}
    return {'status': 'ok', 'scope': scope, 'timestamp': event.get('timestamp'),
            'turn_id': turn_id, 'new_input_tokens': total - cached,
            'cached_input_tokens': cached, 'input_tokens': total,
            'cache_write_input_tokens': usage.get('cache_write_input_tokens'),
            'output_tokens': usage.get('output_tokens'), 'final_reply_included': False}


def main():
    thread_id = os.environ.get('CODEX_THREAD_ID')
    if not thread_id:
        return {'status': 'unavailable', 'reason': 'CODEX_THREAD_ID missing'}
    home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    db = home / 'state_5.sqlite'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2) as connection:
        row = connection.execute('SELECT rollout_path FROM threads WHERE id = ?', (thread_id,)).fetchone()
    if not row:
        return {'status': 'unavailable', 'reason': 'thread not found'}
    return latest_usage(Path(row[0]), thread_id)


if __name__ == '__main__':
    try:
        result = main()
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        result = {'status': 'unavailable', 'reason': type(error).__name__}
    print(json.dumps(result, ensure_ascii=False))
