#!/usr/bin/env python3
"""CPU Pulse: unprivileged telemetry, persistent history, focus-only navigation."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import time

STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'cpu-pulse'
ENV_KEYS = {'HERDR_ENV', 'HERDR_SOCKET_PATH', 'HERDR_WORKSPACE_ID', 'HERDR_TAB_ID', 'HERDR_PANE_ID', 'TMUX', 'TMUX_PANE', 'BOOMUX_SHELL_ID'}
PROFILES = ('power-saver', 'balanced', 'performance')
SYS_CPU = Path('/sys/devices/system/cpu')
CLK = os.sysconf('SC_CLK_TCK')
# Columns of a /proc/stat cpu line. guest and guest_nice are already inside
# user and nice, so they never join the total.
STAT_FIELDS = ('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal')

def read(path):
    try:
        return Path(path).read_text(errors='replace')
    except (OSError, ValueError):
        return ''

def read_int(path):
    try:
        return int(read(path).split()[0])
    except (ValueError, IndexError):
        return None

def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
        return p.stdout if p.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''

def clients():
    try:
        value = json.loads(run(['hyprctl', 'clients', '-j']))
        return [c for c in value if isinstance(c, dict) and isinstance(c.get('pid'), int) and re.fullmatch(r'0x[0-9a-fA-F]+', str(c.get('address', '')))]
    except (ValueError, TypeError):
        return []

def environment(pid):
    # Only these routing identities ever leave this function. No credentials,
    # command lines, or full process environments are persisted.
    return {k: v for s in read(f'/proc/{pid}/environ').split('\0') for k, sep, v in [s.partition('=')] if sep and k in ENV_KEYS}

def process(pid):
    raw = read(f'/proc/{pid}/stat')
    if not raw:
        return None
    try:
        tail = raw[raw.rindex(')') + 2:].split()
        return {'pid': int(pid), 'start': tail[19], 'ppid': int(tail[1]), 'state': tail[0],
                'name': raw[raw.index('(')+1:raw.rindex(')')][:64],
                'ticks': int(tail[11]) + int(tail[12]), 'nice': int(tail[16]), 'threads': int(tail[17])}
    except (ValueError, IndexError):
        return None

def window_for(pid, procs, windows):
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        if pid in windows:
            return windows[pid]
        pid = procs.get(pid, {}).get('ppid', 0)
    return None

def target_for(p, procs, wins):
    windows = {c['pid']: c for c in wins}
    w = window_for(p['pid'], procs, windows)
    env = environment(p['pid'])
    host = {}
    # Boomux terminal titles carry an exact shell id. Focusing that existing
    # window needs no launcher and cannot create or terminate a session.
    shell = env.get('BOOMUX_SHELL_ID', '')
    if shell:
        match = [c for c in wins if str(c.get('title', '')).startswith('boomux:shell:') and str(c.get('title', '')).split(' ')[0].endswith(':' + shell)]
        if match:
            w = match[0]
    if not shell and env.get('HERDR_ENV') == '1' and env.get('HERDR_PANE_ID'):
        sock = env.get('HERDR_SOCKET_PATH') or str(Path.home() / '.config/herdr/herdr.sock')
        for q in procs.values():
            if q['name'] != 'herdr':
                continue
            cw = window_for(q['pid'], procs, windows)
            ce = environment(q['pid'])
            cs = ce.get('HERDR_SOCKET_PATH') or str(Path.home() / '.config/herdr/herdr.sock')
            if cw and cs == sock:
                w = cw
                host = {'kind': 'herdr', 'socket': sock, 'workspace': env.get('HERDR_WORKSPACE_ID', ''), 'tab': env.get('HERDR_TAB_ID', ''), 'pane': env['HERDR_PANE_ID']}
                break
    if not shell and not host and env.get('TMUX') and re.fullmatch(r'%\d+', env.get('TMUX_PANE', '')):
        sock = env['TMUX'].rsplit(',', 2)[0]
        pane = env['TMUX_PANE']
        # Attach only to a client already displaying this pane's session.
        session = run(['tmux', '-S', sock, 'display-message', '-p', '-t', pane, '#{session_id}']).strip()
        for line in run(['tmux', '-S', sock, 'list-clients', '-F', '#{client_pid}\t#{session_id}\t#{client_name}']).splitlines():
            parts = line.split('\t')
            if len(parts) == 3 and parts[0].isdigit() and parts[1] == session:
                cw = window_for(int(parts[0]), procs, windows)
                if cw:
                    w = cw
                    host = {'kind': 'tmux', 'socket': sock, 'pane': pane, 'client': parts[2]}
                    break
    return {'address': w['address'], 'title': str(w.get('title', ''))[:100], 'workspace': str(w.get('workspace', {}).get('name', '')), 'host': host} if w else {}

def all_processes():
    procs = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            p = process(entry.name)
            if p:
                procs[p['pid']] = p
    return procs

def hogs(previous=None, now=None):
    """Top 24 processes by CPU time rate. previous maps (pid, start) -> (ticks, ts)
    from the last scan; a process seen for the first time reports its lifetime
    average instead of being hidden. Returns (rows, ticks) so the daemon can
    carry the new tick table forward."""
    now = now or time.time()
    uptime = float(read('/proc/uptime').split()[0] or 0)
    procs = all_processes()
    ticks = {}
    for p in procs.values():
        key = (p['pid'], p['start'])
        ticks[key] = (p['ticks'], now)
        old = (previous or {}).get(key)
        if old and now - old[1] > 0:
            p['cpu'] = max(0, p['ticks'] - old[0]) / CLK / (now - old[1]) * 100
            p['sampled'] = True
        else:
            age = max(0.5, uptime - int(p['start']) / CLK)
            p['cpu'] = p['ticks'] / CLK / age * 100
            p['sampled'] = False
    wins = clients()
    rows = sorted(procs.values(), key=lambda p: (p['cpu'], p['ticks']), reverse=True)[:24]
    for p in rows:
        try:
            p['owned'] = Path(f"/proc/{p['pid']}").stat().st_uid == os.getuid()
        except OSError:
            p['owned'] = False
        p['target'] = target_for(p, procs, wins) if p['owned'] else {}
    return rows, ticks

def cpu_lines(raw):
    result = {}
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0].startswith('cpu'):
            try:
                result[parts[0]] = [int(v) for v in parts[1:9]]
            except ValueError:
                pass
    return result

def usage(now, then):
    """Busy percentage and per-field breakdown between two /proc/stat cpu rows."""
    delta = [max(0, a - b) for a, b in zip(now, then)] if then else [0] * 8
    total = sum(delta)
    if total <= 0:
        return 0.0, {k: 0.0 for k in STAT_FIELDS}
    breakdown = {k: v / total * 100 for k, v in zip(STAT_FIELDS, delta)}
    return 100 - breakdown['idle'] - breakdown['iowait'], breakdown

def temperatures():
    package, cores, sensors = None, {}, []
    for h in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
        if read(h / 'name').strip() != 'coretemp':
            continue
        for f in sorted(h.glob('temp*_input'), key=lambda f: int(re.sub(r'\D', '', f.name) or 0)):
            label = read(f.with_name(f.name.replace('_input', '_label'))).strip()
            value = read_int(f)
            if value is None:
                continue
            value /= 1000
            if label.startswith('Package id'):
                package = value if package is None else max(package, value)
            elif label.startswith('Core '):
                cores[label[5:]] = value
            sensors.append({'label': label, 'temp': value})
    fallback = None
    for z in sorted(Path('/sys/class/thermal').glob('thermal_zone*'), key=lambda z: int(re.sub(r'\D', '', z.name) or 0)):
        kind = read(z / 'type').strip()
        value = read_int(z / 'temp')
        if value is None or value <= 0:
            continue
        value /= 1000
        if kind in ('x86_pkg_temp', 'TCPU', 'cpu-thermal', 'cpu_thermal', 'soc_thermal', 'acpitz', 'CPU'):
            fallback = value if fallback is None else fallback
            if kind != 'x86_pkg_temp' or package is None:
                sensors.append({'label': kind, 'temp': value})
    return package if package is not None else fallback, cores, sensors[:16]

def frequency():
    base = SYS_CPU / 'cpu0/cpufreq'
    turbo = None
    no_turbo = read_int(SYS_CPU / 'intel_pstate/no_turbo')
    boost = read_int(SYS_CPU / 'cpufreq/boost')
    if no_turbo is not None:
        turbo = no_turbo == 0
    elif boost is not None:
        turbo = boost == 1
    return {'max': read_int(base / 'cpuinfo_max_freq'), 'min': read_int(base / 'cpuinfo_min_freq'), 'base': read_int(base / 'base_frequency'),
            'governor': read(base / 'scaling_governor').strip(), 'driver': read(base / 'scaling_driver').strip(),
            'epp': read(base / 'energy_performance_preference').strip(), 'turbo': turbo}

def metrics(previous=None):
    raw = read('/proc/stat')
    rows = cpu_lines(raw)
    if 'cpu' not in rows:
        raise RuntimeError('Kernel CPU telemetry unavailable')
    ts = time.time()
    old = previous.get('raw', {}) if previous else {}
    elapsed = ts - previous['ts'] if previous else 0
    busy, breakdown = usage(rows['cpu'], old.get('cpu'))
    core_temp, core_temps, sensors = temperatures()
    cores = []
    for name in sorted((k for k in rows if k != 'cpu'), key=lambda k: int(k[3:])):
        index = int(name[3:])
        core_busy, _ = usage(rows[name], old.get(name))
        core_id = read_int(SYS_CPU / f'cpu{index}/topology/core_id')
        cores.append({'id': index, 'core': core_id, 'busy': core_busy,
                      'freq': read_int(SYS_CPU / f'cpu{index}/cpufreq/scaling_cur_freq'),
                      'temp': core_temps.get(str(core_id))})
    threads = len(cores) or 1
    physical = len({c['core'] for c in cores if c['core'] is not None}) or threads
    counters = {}
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0] in ('ctxt', 'processes', 'procs_running', 'procs_blocked', 'intr'):
            counters[parts[0]] = int(parts[1])
    rates = {k: max(0, counters.get(k, 0) - previous.get('counters', {}).get(k, counters.get(k, 0))) / elapsed if elapsed > 0 else 0 for k in ('ctxt', 'processes', 'intr')}
    load = read('/proc/loadavg').split()
    try:
        load1, load5, load15 = (float(v) for v in load[:3])
    except ValueError:
        load1 = load5 = load15 = 0.0
    psi = {}
    for line in read('/proc/pressure/cpu').splitlines():
        parts = line.split()
        psi[parts[0]] = {k: float(v) for k, v in (s.split('=') for s in parts[1:])}
    freq = frequency()
    known = [c['freq'] for c in cores if c['freq']]
    freq['avg'] = sum(known) / len(known) if known else None
    freq['peak'] = max(known) if known else None
    throttle = {'package': read_int(SYS_CPU / 'cpu0/thermal_throttle/package_throttle_count') or 0,
                'core': sum(read_int(f) or 0 for f in SYS_CPU.glob('cpu*/thermal_throttle/core_throttle_count'))}
    watts = None
    energy = read_int('/sys/class/powercap/intel-rapl:0/energy_uj')
    if energy is not None and previous and previous.get('energy') is not None and elapsed > 0 and energy >= previous['energy']:
        watts = (energy - previous['energy']) / 1e6 / elapsed
    model = ''
    for line in read('/proc/cpuinfo').splitlines():
        if line.startswith('model name'):
            model = line.partition(':')[2].strip()
            break
    return {'ts': ts, 'warm': bool(old.get('cpu')), 'busyPct': busy, 'idlePct': 100 - busy, 'breakdown': breakdown, 'cores': cores,
            'threads': threads, 'physical': physical, 'model': model[:80],
            'load': [load1, load5, load15], 'loadPct': load1 / threads * 100,
            'running': counters.get('procs_running', 0), 'blocked': counters.get('procs_blocked', 0),
            'psi': psi, 'rates': rates, 'counters': counters, 'freq': freq, 'temp': core_temp, 'sensors': sensors,
            'throttle': throttle, 'watts': watts, 'energy': energy,
            'profile': run(['powerprofilesctl', 'get']).strip(),
            'uptime': float((read('/proc/uptime').split() or ['0'])[0]), 'raw': rows}

def db_open():
    db = sqlite3.connect(STATE / 'history.sqlite3', timeout=5)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS samples (ts REAL PRIMARY KEY, busy REAL, temp REAL, psi REAL, load REAL, boot TEXT)')
    return db

def record(db, m):
    db.execute('INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?)', (m['ts'], m['busyPct'], m['temp'] if m['temp'] is not None else 0, m['psi'].get('some', {}).get('avg10', 0), m['loadPct'], read('/proc/sys/kernel/random/boot_id').strip()))
    db.execute('DELETE FROM samples WHERE ts < ?', (m['ts']-7*86400,))
    db.commit()

def history(db, seconds, now=None):
    now = now or time.time()
    bucket = max(15, seconds/240)
    # Boot is part of each bucket; never connect a line across a reboot.
    rows = db.execute('SELECT MIN(ts), AVG(busy), MAX(busy), AVG(temp), MAX(psi), COUNT(*), boot FROM samples WHERE ts>=? AND ts<=? GROUP BY CAST(ts/? AS INTEGER), boot ORDER BY MIN(ts)', (now-seconds, now, bucket)).fetchall()
    return {'seconds': seconds, 'bucket': bucket, 'now': now, 'points': rows, 'count': sum(r[5] for r in rows), 'peak': max((r[2] for r in rows), default=0)}

def atomic(name, value):
    path = STATE / name
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, separators=(',', ':'), ensure_ascii=True))
    tmp.replace(path)

def daemon():
    with (STATE / 'collector.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        db = db_open()
        previous = None
        ticks = None
        last_history = last_procs = 0
        rows = []
        while True:
            start = time.monotonic()
            try:
                m = metrics(previous)
                if m['warm'] and start-last_history >= 15:
                    record(db, m)
                    atomic('history.json', {str(s): history(db, s, m['ts']) for s in (3600, 86400, 604800)})
                    last_history = start
                if start-last_procs >= 9:
                    rows, ticks = hogs(ticks, m['ts'])
                    last_procs = start
                m['hogs'] = rows
                if m['warm']:
                    atomic('snapshot.json', m)
                previous = m
            except (OSError, sqlite3.Error, RuntimeError, ValueError) as e:
                print(f'CPU Pulse: {type(e).__name__}: {e}', flush=True)
            time.sleep(max(0.2, 3-(time.monotonic()-start)))

def focus(pid, start):
    # Re-read identity and routing on click; an old snapshot cannot focus a
    # recycled PID or run a command supplied by a window title.
    p = process(pid)
    if not p or p['start'] != start or Path(f'/proc/{pid}').stat().st_uid != os.getuid():
        raise RuntimeError('Process exited or identity changed. Refresh the list.')
    target = target_for(p, all_processes(), clients())
    if not target:
        raise RuntimeError('No existing window or attached session for this process.')
    host = target.get('host', {})
    if host.get('kind') == 'herdr':
        for kind, pattern in [('workspace', r'w[\w-]{1,32}'), ('tab', r'w[\w-]{1,32}:t[\w-]{1,32}'), ('pane', r'w[\w-]{1,32}:p[\w-]{1,32}')]:
            value = host.get(kind, '')
            if not re.fullmatch(pattern, value, re.ASCII):
                continue
            request = {'id': 'cpu-pulse:'+kind, 'method': kind+'.focus', 'params': {kind+'_id': value}}
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2)
                s.connect(host['socket'])
                s.sendall((json.dumps(request)+'\n').encode())
                reply = b''
                while b'\n' not in reply and len(reply) < 65536:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    reply += chunk
                response = json.loads(reply.split(b'\n')[0])
                if response.get('id') != request['id'] or 'error' in response or 'result' not in response:
                    raise RuntimeError('Herdr could not focus this pane.')
    elif host.get('kind') == 'tmux':
        prefix = ['tmux', '-S', host['socket']]
        for cmd in [['select-window', '-t', host['pane']], ['select-pane', '-t', host['pane']], ['switch-client', '-c', host['client'], '-t', host['pane']]]:
            result = subprocess.run(prefix+cmd, capture_output=True, timeout=2)
            if result.returncode:
                raise RuntimeError('tmux could not focus this pane.')
    version = run(['hyprctl', 'version', '-j'])
    try:
        v = json.loads(version)
        match = re.search(r'(\d+)\.(\d+)', v.get('tag', v.get('version', '')))
        lua = bool(match and (int(match[1]), int(match[2])) >= (0, 56))
    except (ValueError, TypeError):
        lua = False
    addr = target['address']
    args = ['hyprctl', 'dispatch'] + ([f'hl.dsp.focus({{ window = "address:{addr}" }})'] if lua else ['focuswindow', 'address:'+addr])
    response = run(args)
    if not response or 'error' in response.lower():
        raise RuntimeError('Window focus failed; the window may have closed.')
    return {'message': 'Focused '+p['name']}

def profile(name):
    # power-profiles-daemon applies the change through polkit as the session
    # user. It is reversible from the same card, and it never touches
    # frequencies, governors, or processes directly.
    if name not in PROFILES:
        raise RuntimeError('Unknown power profile.')
    current = run(['powerprofilesctl', 'get']).strip()
    if not current:
        raise RuntimeError('power-profiles-daemon is not available.')
    if current == name:
        return {'message': 'Power profile is already '+name+'.'}
    try:
        result = subprocess.run(['powerprofilesctl', 'set', name], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('powerprofilesctl did not respond.')
    if result.returncode:
        raise RuntimeError('Profile change refused: '+(result.stderr.strip().splitlines() or ['no reason given'])[-1][:120])
    return {'message': 'Power profile: '+current+' → '+name+'. The clock and temperature will settle over the next few samples.'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['daemon', 'snapshot', 'focus', 'profile'])
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        if args.action == 'daemon':
            daemon()
            return
        if args.action == 'snapshot':
            first = metrics()
            time.sleep(0.5)
            value = metrics(first)
            value['hogs'] = hogs()[0]
        elif args.action == 'focus':
            if len(args.args) != 2 or not args.args[0].isdigit():
                raise RuntimeError('focus needs a PID and a start time.')
            value = focus(int(args.args[0]), args.args[1])
        else:
            if len(args.args) != 1:
                raise RuntimeError('profile needs one name.')
            value = profile(args.args[0])
        print(json.dumps(value))
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
