import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cpu', Path(__file__).resolve().parents[1]/'cpu_pulse.py')
cpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpu)

STAT_A = 'cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 50 0 25 400 25 0 0 0 0 0\ncpu1 50 0 25 400 25 0 0 0 0 0\nintr 1000 0\nctxt 5000\nprocesses 100\nprocs_running 2\nprocs_blocked 1\n'
STAT_B = 'cpu  160 0 70 830 60 0 0 0 0 0\ncpu0 110 0 45 400 25 0 0 0 0 0\ncpu1 50 0 25 430 35 0 0 0 0 0\nintr 1300 0\nctxt 5600\nprocesses 130\nprocs_running 3\nprocs_blocked 0\n'

def stat_reader(raw):
    original = cpu.read
    return lambda p: raw if p == '/proc/stat' else original(p)

class CpuTests(unittest.TestCase):
    def test_busy_excludes_idle_and_iowait(self):
        with patch.object(cpu, 'read', side_effect=stat_reader(STAT_A)), patch.object(cpu.time, 'time', return_value=1000.0):
            first = cpu.metrics()
        self.assertFalse(first['warm'])
        self.assertEqual(first['busyPct'], 0)
        with patch.object(cpu, 'read', side_effect=stat_reader(STAT_B)), patch.object(cpu.time, 'time', return_value=1003.0):
            m = cpu.metrics(first)
        # Delta: user 60, system 20, idle 30, iowait 10 → 120 ticks, 80 busy.
        self.assertTrue(m['warm'])
        self.assertAlmostEqual(m['busyPct'], 80/120*100)
        self.assertAlmostEqual(m['breakdown']['iowait'], 10/120*100)
        self.assertAlmostEqual(m['cores'][0]['busy'], 100)
        self.assertAlmostEqual(m['cores'][1]['busy'], 0)
        self.assertEqual(m['threads'], 2)
        self.assertAlmostEqual(m['rates']['ctxt'], 200)

    def test_missing_telemetry_not_zero_cpu(self):
        with patch.object(cpu, 'read', return_value=''):
            with self.assertRaises(RuntimeError): cpu.metrics()

    def test_counter_reset_never_negative(self):
        with patch.object(cpu, 'read', side_effect=stat_reader(STAT_B)):
            prev = cpu.metrics()
        prev['ts'] -= 3
        with patch.object(cpu, 'read', side_effect=stat_reader(STAT_A)):
            m = cpu.metrics(prev)
        self.assertEqual(m['busyPct'], 0)
        self.assertTrue(all(v >= 0 for v in m['rates'].values()))
        self.assertTrue(all(c['busy'] >= 0 for c in m['cores']))

    def test_process_stat_with_parentheses(self):
        # After comm: state, ppid, ... utime is index 11, stime 12, nice 16, threads 17, starttime 19.
        tail = ['S', '7'] + ['0']*9 + ['300', '100'] + ['0']*3 + ['5', '9', '0', '98765'] + ['0']*5
        with patch.object(cpu, 'read', return_value='12 (strange (name)) ' + ' '.join(tail)):
            p = cpu.process(12)
        self.assertEqual(p['name'], 'strange (name)')
        self.assertEqual(p['start'], '98765'); self.assertEqual(p['ppid'], 7)
        self.assertEqual(p['ticks'], 400); self.assertEqual(p['nice'], 5); self.assertEqual(p['threads'], 9)

    def test_hog_rate_from_previous_ticks_and_lifetime_fallback(self):
        procs = {1: {'pid': 1, 'start': '100', 'ppid': 0, 'name': 'a', 'ticks': 1000, 'nice': 0, 'threads': 1, 'state': 'S'},
                 2: {'pid': 2, 'start': '200', 'ppid': 1, 'name': 'b', 'ticks': 50, 'nice': 0, 'threads': 1, 'state': 'R'}}
        with patch.object(cpu, 'all_processes', return_value=procs), patch.object(cpu, 'clients', return_value=[]), \
             patch.object(cpu, 'target_for', return_value={}), patch.object(cpu, 'read', return_value='1000.0 2000.0\n'):
            rows, ticks = cpu.hogs({(2, '200'): (0, 990.0)}, 1000.0)
        by_pid = {r['pid']: r for r in rows}
        self.assertTrue(by_pid[2]['sampled']); self.assertAlmostEqual(by_pid[2]['cpu'], 50/cpu.CLK/10*100)
        self.assertFalse(by_pid[1]['sampled']); self.assertGreater(by_pid[1]['cpu'], 0)
        self.assertEqual(ticks[(1, '100')][0], 1000)

    def test_ancestry_cycle_is_bounded(self):
        self.assertIsNone(cpu.window_for(5, {5: {'ppid': 6}, 6: {'ppid': 5}}, {}))
        self.assertEqual(cpu.window_for(5, {5: {'ppid': 6}}, {6: {'address': '0xabc'}})['address'], '0xabc')

    def test_environment_allowlist(self):
        with patch.object(cpu, 'read', return_value='TOKEN=secret\0HERDR_PANE_ID=w1:p2\0PASSWORD=secret\0'):
            self.assertEqual(cpu.environment(1), {'HERDR_PANE_ID': 'w1:p2'})

    def test_recycled_pid_cannot_focus(self):
        with patch.object(cpu, 'process', return_value={'start': 'new'}), patch.object(cpu, 'run') as run:
            with self.assertRaises(RuntimeError): cpu.focus(100, 'old')
            run.assert_not_called()

    def test_history_retention_peak_and_boot_gaps(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cpu, 'STATE', Path(d)):
            db = cpu.db_open()
            now = 1000000
            def add(ts, busy, boot):
                db.execute('INSERT INTO samples VALUES(?,?,?,?,?,?)', (ts, busy, 60, 1, 50, boot))
            add(now-604900, 20, 'old')
            add(now-20, 30, 'a'); add(now-18, 80, 'a'); add(now-17, 50, 'b')
            db.commit()
            h = cpu.history(db, 3600, now)
            self.assertEqual(h['count'], 3); self.assertEqual(h['peak'], 80)
            self.assertEqual({p[6] for p in h['points']}, {'a', 'b'})
            with patch.object(cpu, 'read', side_effect=stat_reader(STAT_A)):
                m = cpu.metrics()
            m.update(ts=now, busyPct=40, temp=None)
            cpu.record(db, m)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM samples WHERE ts<?', (now-604800,)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT temp FROM samples WHERE ts=?', (now,)).fetchone()[0], 0)
            db.close()
            db = cpu.db_open(); self.assertEqual(cpu.history(db, 3600, now)['count'], 4); db.close()

    def test_package_temperature_preferred_over_zones(self):
        with tempfile.TemporaryDirectory() as d:
            hw = Path(d)/'hwmon/hwmon0'; hw.mkdir(parents=True)
            (hw/'name').write_text('coretemp\n')
            (hw/'temp1_label').write_text('Package id 0\n'); (hw/'temp1_input').write_text('66000\n')
            (hw/'temp2_label').write_text('Core 4\n'); (hw/'temp2_input').write_text('59000\n')
            zone = Path(d)/'thermal/thermal_zone0'; zone.mkdir(parents=True)
            (zone/'type').write_text('x86_pkg_temp\n'); (zone/'temp').write_text('70000\n')
            original = cpu.Path
            with patch.object(cpu, 'Path', side_effect=lambda p: original(str(p).replace('/sys/class', d))):
                temp, cores, sensors = cpu.temperatures()
        self.assertEqual(temp, 66.0); self.assertEqual(cores, {'4': 59.0})
        self.assertNotIn('x86_pkg_temp', [s['label'] for s in sensors])

    def test_profile_rejects_unknown_and_never_shells_out(self):
        with patch.object(cpu, 'run') as run, patch.object(cpu.subprocess, 'run') as sub:
            with self.assertRaises(RuntimeError): cpu.profile('turbo-max; rm -rf /')
            run.assert_not_called(); sub.assert_not_called()
        with patch.object(cpu, 'run', return_value='balanced\n'), patch.object(cpu.subprocess, 'run') as sub:
            self.assertIn('already', cpu.profile('balanced')['message'])
            sub.assert_not_called()

    def test_unknown_action_rejected(self):
        import subprocess
        p = subprocess.run(['python3', str(Path(cpu.__file__)), 'kill'], capture_output=True)
        self.assertEqual(p.returncode, 2)

if __name__ == '__main__': unittest.main()
