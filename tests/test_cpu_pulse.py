import importlib.util
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cpu', Path(__file__).resolve().parents[1]/'cpu_pulse.py')
cpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpu)

STAT_A = 'cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 50 0 25 400 25 0 0 0 0 0\ncpu1 50 0 25 400 25 0 0 0 0 0\nintr 1000 0\nctxt 5000\nprocesses 100\nprocs_running 2\nprocs_blocked 1\n'
STAT_B = 'cpu  160 0 70 830 60 0 0 0 0 0\ncpu0 110 0 45 400 25 0 0 0 0 0\ncpu1 50 0 25 430 35 0 0 0 0 0\nintr 1300 0\nctxt 5600\nprocesses 130\nprocs_running 3\nprocs_blocked 0\n'

def stat_reader(raw):
    return lambda p: {'/proc/stat': raw, '/proc/uptime': '1000.0 2000.0', '/proc/loadavg': '1 2 3'}.get(str(p), '')

class CpuTests(unittest.TestCase):
    def test_empty_state_home_uses_same_fallback_as_panel(self):
        with patch.dict(cpu.os.environ, {'XDG_STATE_HOME': ''}):
            module = runpy.run_path(cpu.__file__)
        self.assertEqual(module['STATE'], Path.home() / '.local/state/cpu-pulse')

    def test_busy_excludes_idle_and_iowait(self):
        with patch.object(cpu, 'read', side_effect=stat_reader(STAT_A)), patch.object(cpu.time, 'monotonic', return_value=1000.0):
            first = cpu.metrics()
        self.assertFalse(first['warm'])
        self.assertEqual(first['busyPct'], 0)
        with patch.object(cpu, 'read', side_effect=stat_reader(STAT_B)), patch.object(cpu.time, 'monotonic', return_value=1003.0):
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
        prev['monotonic'] -= 3
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

    def test_short_cpu_rows_are_padded_and_malformed_rows_ignored(self):
        rows = cpu.cpu_lines('cpu 1 2 3 4\ncpu0 1 2 3 4\ncpu1 1 2\ncpuoops 1 2 3 4\ncpu2 x 2 3 4')
        self.assertEqual(set(rows), {'cpu', 'cpu0'})
        busy, breakdown = cpu.usage(rows['cpu'], [0] * 8)
        self.assertEqual(busy, 60)
        self.assertEqual(set(breakdown), set(cpu.STAT_FIELDS))

    def test_partial_counter_wrap_discards_interval_but_iowait_may_decrease(self):
        self.assertEqual(cpu.usage([5, 0, 110, 120, 0, 0, 0, 0],
                                   [2**32-5, 0, 100, 100, 0, 0, 0, 0])[0], 0)
        busy, _ = cpu.usage([110, 0, 0, 110, 5, 0, 0, 0], [100, 0, 0, 100, 10, 0, 0, 0])
        self.assertEqual(busy, 50)

    def test_rates_ignore_wall_clock_changes_and_energy_wraps(self):
        def reader(raw, energy):
            base = stat_reader(raw)
            return lambda p: {'/sys/class/powercap/intel-rapl:0/energy_uj': str(energy),
                              '/sys/class/powercap/intel-rapl:0/max_energy_range_uj': '100000000'}.get(str(p), base(p))
        with patch.object(cpu, 'read', side_effect=reader(STAT_A, 99000000)), \
             patch.object(cpu.time, 'time', return_value=1000), patch.object(cpu.time, 'monotonic', return_value=10):
            first = cpu.metrics()
        with patch.object(cpu, 'read', side_effect=reader(STAT_B, 5000000)), \
             patch.object(cpu.time, 'time', return_value=900), patch.object(cpu.time, 'monotonic', return_value=13):
            second = cpu.metrics(first)
        self.assertEqual(second['rates']['ctxt'], 200)
        self.assertEqual(second['watts'], 2)

    def test_missing_optional_telemetry_and_new_online_cpu(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cpu, 'SYS_CPU', Path(d)), \
             patch.object(cpu, 'read', side_effect=stat_reader(STAT_A)), patch.object(cpu, 'run', return_value=''):
            first = cpu.metrics()
        raw = STAT_B.replace('cpu1 ', 'cpu2 ')
        with tempfile.TemporaryDirectory() as d, patch.object(cpu, 'SYS_CPU', Path(d)), \
             patch.object(cpu, 'read', side_effect=stat_reader(raw)), patch.object(cpu, 'run', return_value=''):
            second = cpu.metrics(first)
        self.assertEqual([c['id'] for c in second['cores']], [0, 2])
        self.assertEqual(second['cores'][1]['busy'], 0)
        self.assertIsNone(second['temp'])
        self.assertIsNone(second['freq']['avg'])
        self.assertEqual(second['profile'], '')

    def test_multi_socket_cores_and_temperatures(self):
        def reader(path):
            path = str(path)
            if path.endswith('/topology/core_id'):
                return '0'
            if path.endswith('/topology/physical_package_id'):
                return '1' if '/cpu1/' in path else '0'
            return stat_reader(STAT_A)(path)
        with patch.object(cpu, 'read', side_effect=reader), \
             patch.object(cpu, 'temperatures', return_value=(70, {(0, '0'): 50, (1, '0'): 65}, [])):
            m = cpu.metrics()
        self.assertEqual(m['physical'], 2)
        self.assertEqual([c['temp'] for c in m['cores']], [50, 65])

    def test_frequency_uses_online_cpu_when_cpu_zero_is_offline(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cpu, 'SYS_CPU', Path(d)):
            for index in (0, 1):
                base = Path(d) / f'cpu{index}/cpufreq'
                base.mkdir(parents=True)
                (base.parent / 'online').write_text(str(index))
                (base / 'scaling_driver').write_text('offline' if index == 0 else 'acpi-cpufreq')
            self.assertEqual(cpu.frequency()['driver'], 'acpi-cpufreq')

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

    def test_hogs_missing_uptime_and_monotonic_default(self):
        procs = {100: {'pid': 100, 'start': '10', 'ticks': 1000}}
        with patch.object(cpu, 'all_processes', return_value=procs), patch.object(cpu, 'clients', return_value=[]), \
             patch.object(cpu, 'target_for', return_value={}), \
             patch.object(cpu, 'read', return_value=''), patch.object(cpu.time, 'monotonic', return_value=10) as clock:
            rows, ticks = cpu.hogs()
            self.assertEqual(rows[0]['cpu'], 0)
            self.assertEqual(ticks[(100, '10')], (1000, 10))
            clock.assert_called_once()

    def test_ancestry_cycle_is_bounded(self):
        self.assertIsNone(cpu.window_for(5, {5: {'ppid': 6}, 6: {'ppid': 5}}, {}))
        self.assertEqual(cpu.window_for(5, {5: {'ppid': 6}}, {6: {'address': '0xabc'}})['address'], '0xabc')

    def test_environment_allowlist(self):
        with patch.object(cpu, 'read', return_value='TOKEN=secret\0HERDR_PANE_ID=w1:p2\0PASSWORD=secret\0'):
            self.assertEqual(cpu.environment(1), {'HERDR_PANE_ID': 'w1:p2'})

    def test_window_addresses_are_validated_independently_of_titles(self):
        windows = [{'pid': 10, 'address': '0xabc', 'title': '$(touch /tmp/not-run)'},
                   {'pid': 11, 'address': '0xabc" }); os.execute("bad")', 'title': 'normal'}]
        with patch.object(cpu, 'run', return_value=json.dumps(windows)):
            self.assertEqual(cpu.clients(), windows[:1])

    def test_recycled_pid_cannot_focus(self):
        with patch.object(cpu, 'process', return_value={'start': 'new'}), patch.object(cpu, 'run') as run:
            with self.assertRaises(RuntimeError): cpu.focus(100, 'old')
            run.assert_not_called()

    def test_pid_recycled_during_routing_cannot_focus(self):
        with patch.object(cpu, 'process', side_effect=[{'start': 'old', 'pid': 100}, {'start': 'new'}]), \
             patch.object(cpu.Path, 'stat', return_value=SimpleNamespace(st_uid=cpu.os.getuid())), \
             patch.object(cpu, 'all_processes', return_value={}), patch.object(cpu, 'clients', return_value=[]), \
             patch.object(cpu, 'target_for', return_value={'address': '0xabc', 'host': {}}), \
             patch.object(cpu, 'run') as run, patch.object(cpu.subprocess, 'run') as sub:
            with self.assertRaises(RuntimeError): cpu.focus(100, 'old')
            run.assert_not_called(); sub.assert_not_called()

    def test_boomux_requires_exact_shell_id(self):
        wins = [{'pid': 20, 'address': '0xa', 'title': 'boomux:shell:prefix:a'},
                {'pid': 21, 'address': '0xb', 'title': 'boomux:shell:a task'}]
        with patch.object(cpu, 'environment', return_value={'BOOMUX_SHELL_ID': 'a'}):
            self.assertEqual(cpu.target_for({'pid': 100}, {}, wins)['address'], '0xb')

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
            self.assertIsNone(db.execute('SELECT temp FROM samples WHERE ts=?', (now,)).fetchone()[0])
            db.close()
            db = cpu.db_open(); self.assertEqual(cpu.history(db, 3600, now)['count'], 4); db.close()

    def test_empty_history_and_missing_temperatures(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cpu, 'STATE', Path(d)):
            db = cpu.db_open()
            empty = cpu.history(db, 3600, now=0)
            self.assertEqual((empty['points'], empty['count'], empty['peak'], empty['now']), ([], 0, 0, 0))
            for ts, temp in [(1, 60), (2, None), (3, 0)]:
                db.execute('INSERT INTO samples VALUES(?,?,?,?,?,?)', (ts, 20, temp, 0, 0, 'boot'))
            self.assertEqual(cpu.history(db, 3600, now=10)['points'][0][3], 60)
            db.close()

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
        self.assertEqual(temp, 66.0); self.assertEqual(cores, {(0, '4'): 59.0})
        self.assertNotIn('x86_pkg_temp', [s['label'] for s in sensors])

    def test_temperature_core_ids_do_not_collide_across_packages(self):
        with tempfile.TemporaryDirectory() as d:
            for package in (0, 1):
                hw = Path(d) / f'hwmon/hwmon{package}'
                hw.mkdir(parents=True)
                for name, value in {'name': 'coretemp', 'temp1_label': f'Package id {package}',
                                    'temp2_label': 'Core 0', 'temp2_input': str(50000 + package * 10000)}.items():
                    (hw / name).write_text(value)
            original = cpu.Path
            with patch.object(cpu, 'Path', side_effect=lambda p: original(str(p).replace('/sys/class', d))):
                _, cores, _ = cpu.temperatures()
        self.assertEqual(cores, {(0, '0'): 50, (1, '0'): 60})

    def test_profile_rejects_unknown_and_never_shells_out(self):
        with patch.object(cpu, 'run') as run, patch.object(cpu.subprocess, 'run') as sub:
            with self.assertRaises(RuntimeError): cpu.profile('turbo-max; rm -rf /')
            run.assert_not_called(); sub.assert_not_called()
        with patch.object(cpu, 'run', return_value='balanced\n'), patch.object(cpu.subprocess, 'run') as sub:
            self.assertIn('already', cpu.profile('balanced')['message'])
            sub.assert_not_called()

    def test_profile_missing_service_and_refused_change(self):
        with patch.object(cpu, 'run', return_value=''), patch.object(cpu.subprocess, 'run') as sub:
            with self.assertRaisesRegex(RuntimeError, 'not available'): cpu.profile('performance')
            sub.assert_not_called()
        with patch.object(cpu, 'run', return_value='balanced'), \
             patch.object(cpu.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='unsupported')) as sub:
            with self.assertRaisesRegex(RuntimeError, 'unsupported'): cpu.profile('performance')
            self.assertEqual(sub.call_args.args[0], ['powerprofilesctl', 'set', 'performance'])
            self.assertNotIn('shell', sub.call_args.kwargs)

    def test_unknown_action_rejected(self):
        import subprocess
        p = subprocess.run(['python3', str(Path(cpu.__file__)), 'kill'], capture_output=True)
        self.assertEqual(p.returncode, 2)

if __name__ == '__main__': unittest.main()
