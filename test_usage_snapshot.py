import json
import tempfile
import unittest
from pathlib import Path
from usage_snapshot import latest_usage, reverse_lines


class UsageTests(unittest.TestCase):
    def read_events(self, events):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'log.jsonl'
            path.write_text('\n'.join(json.dumps(x) for x in events) + '\n', encoding='utf-8')
            return latest_usage(path, 'this-chat')

    def test_turn_snapshot_is_not_summed(self):
        def record(total, cached):
            return {'type': 'token_usage_record', 'payload': {
                'thread_id': 'this-chat', 'turn_id': 'turn',
                'turn_token_usage': {'input_tokens': total, 'cached_input_tokens': cached}}}
        result = self.read_events([record(100, 70), record(180, 130)])
        self.assertEqual((result['new_input_tokens'], result['cached_input_tokens']), (50, 130))

    def test_previous_turn_and_other_chat_are_not_used(self):
        result = self.read_events([
            {'type': 'token_usage_record', 'payload': {'thread_id': 'this-chat',
             'turn_token_usage': {'input_tokens': 100, 'cached_input_tokens': 70}}},
            {'type': 'event_msg', 'payload': {'type': 'task_started'}},
            {'type': 'token_usage_record', 'payload': {'thread_id': 'other-chat',
             'turn_token_usage': {'input_tokens': 200, 'cached_input_tokens': 100}}}])
        self.assertEqual(result['status'], 'unavailable')

    def test_reverse_lines_cross_chunk_and_partial_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'log.jsonl'
            path.write_bytes(b'first\n' + b'x' * 70000 + b'\nlast\n')
            self.assertEqual(list(reverse_lines(path)), [b'', b'last', b'x' * 70000, b'first'])
            self.assertEqual(list(reverse_lines(path, limit=10)), [b'', b'last'])


if __name__ == '__main__':
    unittest.main()
