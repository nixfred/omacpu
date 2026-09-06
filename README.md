# CPU Pulse

An animated, glowing processor die for the Omarchy top bar. Green with idle headroom → yellow at 50% busy → dark red when the processor is pegged. Every core is a cell on the die that brightens with its own load, and a clock beam sweeps faster as load rises. Left-click opens the dashboard; right-click offers four saved readouts: percentage busy, percentage idle, package temperature, average clock. All readouts use one decimal and explicit units.

CPU Pulse is the sibling of [RAM Pulse](https://github.com/nixfred/ram.plugin.omarchy): same chip, same colours, same dashboard layout, so the two sit together on the bar.

The dashboard includes:

- Animated die with per-thread cells and orbiting charge, busy percentage, average and peak clock, load average against thread count, and CPU pressure (PSI).
- Continuous 1-hour, 24-hour and 7-day history of busy percentage and package temperature, with the per-bucket busy peak as a faint envelope and hover readings. Missing history is left blank; shutdowns and recording gaps break the trace.
- Every thread: load bar, delivered clock and core temperature for each logical CPU.
- Top 24 processes by CPU time, eight per page, with thread counts. Click to focus the existing app or attached Herdr/tmux pane. Exact Boomux terminal titles can resolve an existing terminal too. Background processes report details. Browser children focus their browser window, not an individual tab.
- Processor lab with the full time breakdown (user, system, nice, I/O wait, IRQ, steal), context switches, interrupts, fork rate, runnable and blocked task counts, full CPU pressure, frequency driver and governor, turbo state, throttle count, and every CPU temperature sensor.
- Power profile switching through `powerprofilesctl` (power-saver, balanced, performance). This goes through power-profiles-daemon and polkit as the session user; it is immediately reversible from the same card.

There are no process termination, renice, affinity, frequency locking, or privileged tuning actions. Processes and window identities are revalidated on every focus click. Session routing uses argument arrays and validated IDs, never interpolated shell commands. Profile names are checked against a fixed list. No process command lines or credentials are saved.

## Install

Requires an existing Omarchy Quickshell desktop, Python 3, systemd user services and Hyprland. No additional Python packages. `power-profiles-daemon` is optional; without it the profile card is inert.

```sh
git clone https://github.com/nixfred/omacpu.git
cd omacpu
python3 install.py
```

Installs under `~/.config/omarchy/plugins/nixfred.cpu-pulse`, appends to the far-right bar, and enables `cpu-pulse.service` for the graphical session. Existing files and bar layout are backed up under `~/.local/state/omarchy/backups/cpu-pulse-TIMESTAMP/`.

The recorder runs independently of the shell/popup: metrics every 3 seconds, processes every 9 seconds, history every 15 seconds. SQLite retains seven days (up to 40,320 samples), downsampled to ~240 points per displayed range; per-bucket peaks are retained. State is private (`0700` directory / `0600` files) in `$XDG_STATE_HOME/cpu-pulse` or `~/.local/state/cpu-pulse`. History stores aggregate metrics only. The latest snapshot contains process names/PIDs/window titles and is replaced, not logged. Closed panels stop their large animations.

## Controls and diagnosis

```sh
omarchy-shell nixfred.cpu-pulse open
omarchy-shell nixfred.cpu-pulse modes
omarchy-shell nixfred.cpu-pulse status
systemctl --user status cpu-pulse.service
journalctl --user -u cpu-pulse.service
python3 cpu_pulse.py snapshot          # one-shot JSON, no daemon needed
python3 -m unittest discover -s tests -v
node tests/test_model.cjs
omarchy plugin validate .
```

Left/right arrows change dashboard tabs. Escape closes. Keys 1–4 select modes in the right-click picker. Inline bar setting `animated: false` disables die animations.

Disable with `omarchy plugin disable nixfred.cpu-pulse` and `systemctl --user disable --now cpu-pulse.service`. This stops only this plugin's telemetry service; historical data stays available. Restore the timestamped `shell.json` backup only if you also intend to restore that earlier layout.

## Accounting

Busy is everything in `/proc/stat` except `idle` and `iowait`, the same definition `top` uses. Guest time is already inside user time and is not counted twice. Per-process percentages are of one thread, so a multi-threaded process can exceed 100%; the bar beneath each row shows its share of the whole processor. A process seen for the first time shows its lifetime average until the next 9-second sample.

The clock is `scaling_cur_freq` averaged across threads. On `intel_pstate` and similar drivers this is the delivered frequency including idle time, so a mostly idle thread reads low even when its bursts run at turbo. The ceiling is `cpuinfo_max_freq`.

Temperature prefers the `coretemp` package sensor, then the `x86_pkg_temp`, `TCPU` or SoC thermal zone. Core temperatures map through `topology/core_id`, so sibling threads share one reading. Package power is shown only when RAPL energy counters are readable without privilege, which most distributions do not allow.

References: [Linux /proc/stat](https://docs.kernel.org/filesystems/proc.html), [PSI](https://docs.kernel.org/accounting/psi.html), [cpufreq sysfs](https://docs.kernel.org/admin-guide/pm/cpufreq.html), [intel_pstate](https://docs.kernel.org/admin-guide/pm/intel_pstate.html), [power-profiles-daemon](https://gitlab.freedesktop.org/upower/power-profiles-daemon).
