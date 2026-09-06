import datetime
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


class InstallTests(unittest.TestCase):
    def test_string_entries_missing_sections_and_repeat_install(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config = home / '.config/omarchy/shell.json'
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({'bar': {'layout': {
                'left': ['omarchy.clock', 'nixfred.cpu-pulse'],
                'right': [{'id': 'another.plugin', 'option': 42}]
            }}, 'unrelated': True}))
            times = [datetime.datetime(2026, 9, 5, 12, 0, 0, i) for i in (1, 2)]
            with patch.object(Path, 'home', return_value=home), patch('subprocess.run'), \
                 patch('datetime.datetime') as clock, patch('builtins.print'):
                clock.now.side_effect = times
                for _ in times:
                    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'install.py'))
            data = json.loads(config.read_text())
            self.assertTrue(data['unrelated'])
            self.assertEqual(data['bar']['layout'], {
                'left': ['omarchy.clock'], 'center': [],
                'right': [{'id': 'another.plugin', 'option': 42},
                          {'id': 'nixfred.cpu-pulse', 'displayMode': 0, 'animated': True}]
            })
            self.assertEqual(len(list((home / '.local/state/omarchy/backups').iterdir())), 2)


if __name__ == '__main__':
    unittest.main()
