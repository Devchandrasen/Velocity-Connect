#!/usr/bin/env python3
"""Opt-in, foreground, serial revision06 launcher. No rebuilds or automatic retries.

prepare only freezes three complete focused plans; admit/status never simulate.
Run the frozen runtime copy after reviewing admission. All limits are operational,
not statistical stopping rules. This module never computes performance statistics.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from itertools import product
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

try:
    from . import run_vehcom_validation as base
except ImportError:
    import run_vehcom_validation as base

GIB, MIB = 2**30, 2**20
PIN_ROOT = Path('/home/codex/buildprovenance/velocity-em-bridge-r05-portable-20260907')
BINARY_SHA = 'a57f40ab95bf1a3b4edb69dc564e7b39f4a821710b751898529adb8885755d8d'
PIN_SHA = '2fa3af7a09ff56baeef5ae9bba61f82ca8b03f452cfce894431b522ea7ce8467'
SOURCE_SHA = '4ee0328e2897055f1d5be22c857847c25a16cf69f48b0648c6abcd18a6ec4c79'
RESOURCE_EVIDENCE = Path('/mnt/w/Velocity-Connect-Revision06/resource-pilot-01/resource_pilot_result.json')
RESOURCE_EVIDENCE_SHA = '1969eea91ec44e7ce30294f53607996681ded700cba85aea8ef034c78aaff288'
RESOURCE_PILOT_MANIFEST_SHA = 'ecb18738171f5c6575658b90f38ad0318e3509b423b4f42ffc11e736a5c83fa8'
SEED_BASE, RUN_BASE = 860001, 86000001
ORDER = ('principal', 'channel-sensitivity', 'load')
COUNTS = {'principal': 160, 'channel-sensitivity': 160, 'load': 360}
# One-UE policy revised BEFORE preparation from the capped resource-only pilot.
# These remain enforced reservations, NOT predicted maxima for every channel.
POLICY = {name: {'timeout_s': 43200 if name == 'load' else 1800,
                 'row_bytes': (256 if name == 'load' else 16) * MIB,
                 'address_space_bytes': 4 * GIB if name == 'load' else 512 * MIB,
                 'host_start_bytes': 6 * GIB if name == 'load' else 1536 * MIB,
                 'wsl_start_bytes': 6 * GIB if name == 'load' else 1536 * MIB}
          for name in ORDER}
DISK_RESERVE = 5 * GIB
MEMORY_FLOOR = GIB
SNAPSHOT_FILES = ('scripts/run_vehcom_revision06.py', 'scripts/run_vehcom_validation.py',
                  'scripts/analyze_vehcom_validation.py',
                  'reproducibility/vehcom_campaign_protocol.md',
                  'reproducibility/vehcom_revision06_execution.md')


def frozen_rows(seed_base=SEED_BASE, run_base=RUN_BASE):
    rows = {p: base.build_rows(p, seed_base=seed_base, run_base=run_base) for p in ORDER}
    for p in ORDER:
        base.validate_rows(rows[p])
        if len(rows[p]) != COUNTS[p]:
            raise ValueError('Frozen 160+160+360 contract changed')
    return rows


def verify_libraries(pin):
    libraries = pin.get('library_sha256', {})
    if not libraries:
        raise ValueError('Missing shared-library pin')
    for path, expected in libraries.items():
        if base.sha256(path) != expected:
            raise ValueError(f'Pinned shared library changed: {path}')


def inspect_pin(*, execute_help=True):
    pin_file = PIN_ROOT / 'em_bridge_build_pin_v1.json'
    if base.sha256(pin_file) != PIN_SHA:
        raise ValueError('Wrong revision05 final provenance pin')
    pin = json.loads(pin_file.read_text(encoding='utf-8'))
    verify_libraries(pin)
    if execute_help:
        result = base.inspect_binary(PIN_ROOT / 'hsr_velocity_connect', pin_file, PIN_ROOT / 'source')
    else:
        # Preparation during a coordinated HFSS run must not start even PrintHelp.
        manifest_file = RESOURCE_EVIDENCE.with_name('resource_pilot.json')
        if base.sha256(manifest_file) != RESOURCE_PILOT_MANIFEST_SHA:
            raise ValueError('Recorded resource-pilot provenance changed')
        result = json.loads(manifest_file.read_text(encoding='utf-8'))['provenance']
        if base.sha256(result['binary']) != BINARY_SHA:
            raise ValueError('Pinned binary changed')
        for relative, expected in result['source_sha256'].items():
            if base.sha256(base.contained(PIN_ROOT / 'source', relative)) != expected:
                raise ValueError(f'Pinned source changed: {relative}')
        result['help_evidence'] = 'Recorded in resource-pilot-01; binary/source/library hashes rechecked without process launch'
    if result['binary_sha256'] != BINARY_SHA or result['source_bundle_sha256'] != SOURCE_SHA:
        raise ValueError('Wrong revision05 final binary/source bundle')
    return result


def resource_qualification():
    if base.sha256(RESOURCE_EVIDENCE) != RESOURCE_EVIDENCE_SHA:
        raise ValueError('Resource qualification artifact changed or missing')
    result = json.loads(RESOURCE_EVIDENCE.read_text(encoding='utf-8'))
    if (result['pilot_status'] != 'process_succeeded_unanalyzed' or result['returncode'] != 0
            or result['gnu_time_maximum_rss_bytes'] != 79134720):
        raise ValueError('Unexpected resource qualification outcome')
    return {'path': str(RESOURCE_EVIDENCE), 'sha256': RESOURCE_EVIDENCE_SHA,
            'result': result, 'scope': 'One DL direct-composite row; not a channel/load cost guarantee'}


def legacy_config_identities(path):
    """Reserve the entire research_campaign.py Cartesian design, even if aborted."""
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    factors = [config[k] for k in ('scenarios', 'speeds_kmph', 'distances_m', 'num_ues_values', 'seeds')]
    if any(not isinstance(values, list) or not values for values in factors):
        raise ValueError(f'Incomplete legacy identity design: {path}')
    start = int(config['run_base'])
    if start < 1 or any(int(seed) < 1 for seed in config['seeds']):
        raise ValueError(f'Invalid legacy identity range: {path}')
    return [(int(cell[-1]), start + i) for i, cell in enumerate(product(*factors))]


def history_check(rows, roots, prior_plans=()):
    """Read all discovered plans AND legacy single-run identities, never metrics."""
    seeds = {r['seed'] for family in rows.values() for r in family}
    runs = {r['run'] for family in rows.values() for r in family}
    seen, evidence = set(), []
    paths = list(prior_plans)
    for root in roots:
        root = Path(root).resolve(strict=True)
        paths.extend(root.rglob('plan.json'))
        paths.extend(root.rglob('campaign_config.json'))
        paths.extend(root.rglob('single_run.csv'))
    configs = {Path(p).resolve(): legacy_config_identities(p) for p in paths
               if Path(p).name == 'campaign_config.json'}
    for path in sorted(map(Path, paths)):
        path = path.resolve(strict=True)
        if path in seen:
            continue
        seen.add(path)
        if path.is_dir():
            path = path / 'plan.json'
        details = {}
        if path.name == 'plan.json':
            prior = base.load_plan(path.parent)
            identifiers = [(r['seed'], r['run']) for r in prior['rows']]
        elif path.name == 'campaign_config.json':
            identifiers = configs[path]
        else:
            try:
                identifiers = [(int(r['seed']), int(r['run']))
                               for r in base.read_csv(path, ('seed', 'run'))]
                if not identifiers:
                    raise ValueError('Header-only interrupted result')
            except (ValueError, KeyError) as exc:
                config = next((parent / 'campaign_config.json' for parent in path.parents
                               if parent / 'campaign_config.json' in configs), None)
                if config is None:
                    raise ValueError(f'Unusable history without declared identity fallback: {path}: {exc}') from exc
                identifiers = configs[config]
                details = {'malformed_result_retained': str(exc), 'identity_source': str(config),
                           'identity_source_sha256': base.sha256(config),
                           'rule': 'Reserve entire declared legacy campaign; no failed row discarded'}
        if any(s in seeds or r in runs for s, r in identifiers):
            raise ValueError(f'Historical seed or run overlap: {path}; choose fresh bases')
        evidence.append({'path': str(path), 'sha256': base.sha256(path), 'identities': len(identifiers), **details})
    if not evidence:
        raise ValueError('No historical identities inspected; specify populated --history-root')
    return evidence


def prepare(out, *, history_roots, prior_plans=(), seed_base=SEED_BASE, run_base=RUN_BASE,
            backing_store=Path('/mnt/c'), history_scope_note='Only supplied roots inspected; uniqueness outside them is unverified'):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Output already exists; never reuse or overwrite a preparation')
    verify_drive_mount(out)
    backing_store = Path(backing_store).resolve(strict=True)
    rows = frozen_rows(seed_base, run_base)
    history = history_check(rows, history_roots, prior_plans)
    qualification = resource_qualification()
    provenance = inspect_pin(execute_help=False)
    repo = Path(__file__).resolve().parents[1]
    # Snapshot Python/protocol files only. C++ already has a verified immutable source/.
    inputs = {rel: (repo / rel).read_bytes() for rel in SNAPSHOT_FILES}
    out.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for rel, data in inputs.items():
        path = out / 'runtime' / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f:
            f.write(data)
        hashes[rel] = base.sha256(path)
    plans = {}
    for family in ORDER:
        plan = base.plan_campaign(out / family, provenance, profile=family,
                                  seed_base=seed_base, run_base=run_base)
        plans[family] = plan['plan_sha256']
    manifest = {'schema': 1, 'created_utc': base.utc(), 'out': str(out),
                'seed_base': seed_base, 'run_base': run_base, 'order': list(ORDER),
                'counts': COUNTS, 'policies': POLICY, 'disk_reserve_bytes': DISK_RESERVE,
                'memory_floor_bytes': MEMORY_FLOOR, 'backing_store': str(backing_store),
                'history_scope': {'roots': sorted(str(Path(p).resolve()) for p in history_roots),
                                  'prior_plans': sorted(str(Path(p).resolve()) for p in prior_plans),
                                  'global_uniqueness_verified': False, 'reviewed_scope_note': history_scope_note},
                'history': history, 'runtime_sha256': hashes, 'plan_sha256': plans,
                'resource_qualification': qualification,
                'evidence_boundary': base.BOUNDARY, 'execution_started': False}
    manifest['manifest_sha256'] = base.digest(manifest)
    # Written LAST: incomplete preparation is unusable and is never repaired silently.
    base.write_json_new(out / 'revision06.json', manifest)
    return {'planned_rows': 680, 'execution_started': False, 'manifest_sha256': manifest['manifest_sha256']}


def load(out):
    out = Path(out).resolve()
    m = json.loads((out / 'revision06.json').read_text(encoding='utf-8'))
    expected = m.pop('manifest_sha256')
    if base.digest(m) != expected or m['schema'] != 1 or m['out'] != str(out):
        raise ValueError('Revision06 manifest mismatch; do not move or edit an active campaign')
    m['manifest_sha256'] = expected
    if base.sha256(m['resource_qualification']['path']) != m['resource_qualification']['sha256']:
        raise ValueError('Frozen resource qualification changed')
    if (m['counts'] != COUNTS or m['order'] != list(ORDER) or m['policies'] != POLICY
            or m['disk_reserve_bytes'] != DISK_RESERVE or m['memory_floor_bytes'] != MEMORY_FLOOR):
        raise ValueError('Frozen revision06 operational contract changed')
    for rel in SNAPSHOT_FILES:
        if base.sha256(base.contained(out / 'runtime', rel)) != m['runtime_sha256'][rel]:
            raise ValueError(f'Frozen runtime changed: {rel}')
    for rel, path in [('scripts/run_vehcom_revision06.py', __file__),
                      ('scripts/run_vehcom_validation.py', base.__file__)]:
        if base.sha256(path) != m['runtime_sha256'][rel]:
            raise ValueError('Use the original frozen runtime copy, not edited workspace scripts')
    plans = {p: base.load_plan(out / p) for p in ORDER}
    rows = frozen_rows(m['seed_base'], m['run_base'])
    for family, plan in plans.items():
        if plan['plan_sha256'] != m['plan_sha256'][family] or plan['rows'] != rows[family]:
            raise ValueError('Frozen focused plan differs from revision06 manifest')
    return m, plans


def verify_drive_mount(path):
    """Never fall back from an absent /mnt/<drive> to the WSL root filesystem."""
    parts = Path(path).parts
    if os.name == 'posix' and len(parts) >= 3 and parts[1] == 'mnt' and len(parts[2]) == 1:
        mount = Path('/mnt') / parts[2]
        if not mount.is_mount():
            raise ValueError(f'Required Windows drive is not mounted: {mount}')


def resource_snapshot(out, backing_store):
    """Fresh host + WSL checks. Missing Windows interop/probe fails CLOSED."""
    if os.name != 'posix' or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise ValueError('Real admission/execution requires WSL on this Windows host')
    verify_drive_mount(out)
    verify_drive_mount(backing_store)
    shell = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                             '-Command', '(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'],
                            capture_output=True, text=True, timeout=15, check=True)
    host = int(result.stdout.strip()) * 1024
    mem = {line.split(':')[0]: int(line.split()[1]) * 1024
           for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) == 3}
    out = Path(out).resolve()
    while not out.exists():
        out = out.parent
    return {'utc': base.utc(), 'host_available_bytes': host,
            'wsl_available_bytes': mem['MemAvailable'],
            'output_free_bytes': shutil.disk_usage(out).free,
            'backing_free_bytes': shutil.disk_usage(backing_store).free}


def admission(policy, snapshot, pending):
    limits = {'host_available_bytes': policy['host_start_bytes'],
              'wsl_available_bytes': policy['wsl_start_bytes'],
              'output_free_bytes': DISK_RESERVE + pending * policy['row_bytes'],
              'backing_free_bytes': DISK_RESERVE}
    reasons = resource_failures(snapshot, limits)
    return {'admitted': not reasons, 'reasons': reasons, 'required_bytes': limits,
            'snapshot': snapshot, 'remaining_rows': pending,
            'timeout_ceiling_s': pending * policy['timeout_s'], 'execution_started': False}


def resource_failures(snapshot, limits):
    reasons = []
    for key, minimum in limits.items():
        value = snapshot.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
            reasons.append(f'{key} below required {minimum} bytes or unavailable')
    return reasons


def report(out, plans):
    families = {p: base.status_report(plans[p], base.read_ledger(Path(out) / p, plans[p])) for p in ORDER}
    counts = Counter()
    for value in families.values():
        counts.update(value['status_counts'])
    return {'expected_rows': 680, 'status_counts': dict(counts), 'families': families,
            'all_680_succeeded': counts.get('succeeded', 0) == 680,
            'statistics': None, 'evidence_boundary': base.BOUNDARY}


def directory_bytes(*paths):
    return sum(p.stat().st_size for root in paths for p in Path(root).rglob('*') if p.is_file())


class OperationalStop(Exception):
    """An in-flight operational failure, never retried or used for partial stats."""


def bounded_execute(command, cwd, stdout, stderr, timeout, *, policy, probe, raw, usage=None):
    """One child only; OS address-space/file limits and sampled aggregate guards."""
    if os.name != 'posix':
        raise ValueError('Simulator execution is WSL-only')
    import resource

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (policy['address_space_bytes'],) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (policy['row_bytes'],) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', LC_ALL='C')
    started, next_probe = time.monotonic(), 0.0
    usage = usage if usage is not None else {}
    usage.update(sampled_max_rss_bytes=0, sampled_max_virtual_bytes=0,
                 measurement='Sampled /proc status high-water marks; may miss final allocation, not a certified peak')
    with stdout.open('xb') as out, stderr.open('xb') as err:
        proc = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=err, env=env,
                                start_new_session=True, preexec_fn=limits)
        try:
            while True:
                try:
                    process_memory = {line.split(':')[0]: int(line.split()[1]) * 1024
                                      for line in Path(f'/proc/{proc.pid}/status').read_text().splitlines()
                                      if line.startswith(('VmHWM:', 'VmPeak:'))}
                    for key, field in [('sampled_max_rss_bytes', 'VmHWM'),
                                       ('sampled_max_virtual_bytes', 'VmPeak')]:
                        usage[key] = max(usage[key], process_memory.get(field, 0))
                except FileNotFoundError:
                    pass
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                if directory_bytes(raw, stdout.parent) > policy['row_bytes']:
                    raise OperationalStop('Aggregate row storage limit exceeded')
                if time.monotonic() >= next_probe:
                    try:
                        snap = probe()
                        failures = resource_failures(snap, {
                            'host_available_bytes': policy.get('live_memory_floor_bytes', MEMORY_FLOOR),
                            'wsl_available_bytes': policy.get('live_memory_floor_bytes', MEMORY_FLOOR),
                            'output_free_bytes': DISK_RESERVE,
                            'backing_free_bytes': DISK_RESERVE})
                        if failures:
                            raise OperationalStop('Live resource floor crossed/unavailable: ' + '; '.join(failures))
                    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                        raise OperationalStop(f'Live resource probe unavailable: {exc}') from exc
                    next_probe = time.monotonic() + 5
                if time.monotonic() - started >= timeout:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    return proc.wait(timeout=min(1, max(.01, timeout - (time.monotonic() - started))))
                except subprocess.TimeoutExpired:
                    pass
        finally:
            try:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)  # Only the group created above.
                    except ProcessLookupError:
                        pass  # Child exited between poll and kill; still reap it.
            finally:
                proc.wait()


def execute_row(out, plan, row, policy, executor, probe, admission_check=None):
    raw = base.contained(out, 'raw/' + row['row_id'])
    logs = base.contained(out, 'logs/' + row['row_id'])
    command = [plan['provenance']['binary']] + [f'--{k}={v}' for k, v in row['options'].items()] + [f'--outDir={raw}']
    base.append_event(out, plan, row, 'running', command=command, timeout_s=policy['timeout_s'],
                      revision06_limits=policy, resource_admission=admission_check)
    started, status, details, stop = time.monotonic(), 'failed', {}, False
    usage = {}
    try:
        raw.mkdir(parents=True, exist_ok=False)
        logs.mkdir(parents=True, exist_ok=False)
        rc = executor(command, plan['provenance']['source_root'], logs / 'stdout.log',
                      logs / 'stderr.log', policy['timeout_s'], policy=policy, probe=probe, raw=raw, usage=usage)
        details['returncode'] = rc
        if rc != 0:
            raise ValueError(f'Binary exited with code {rc}')
        if directory_bytes(raw, logs) > policy['row_bytes']:
            raise OperationalStop('Completed output exceeded row storage limit')
        base.validate_result(raw, row)
        if not all((raw / name).is_file() for name in base.RAW_FILES):
            raise ValueError('Required raw output absent')
        details['raw_sha256'] = {p.relative_to(raw).as_posix(): base.sha256(base.contained(raw, p.relative_to(raw)))
                                 for p in sorted(raw.rglob('*')) if p.is_file()}
        base.verify_inputs(plan)
        verify_libraries(plan['provenance']['pin'])
        status = 'succeeded'
    except subprocess.TimeoutExpired as exc:
        status, details['error'] = 'timeout', str(exc)
    except (KeyboardInterrupt, OperationalStop) as exc:
        status, details['error'], stop = 'interrupted', f'Operational stop; no retry: {exc}', True
    except (OSError, ValueError, KeyError) as exc:
        details['error'] = f'{type(exc).__name__}: {exc}'
    details['log_sha256'] = {p.relative_to(out).as_posix(): base.sha256(p) for p in sorted(logs.glob('*.log')) if p.is_file()}
    details['elapsed_wall_s'] = time.monotonic() - started
    details['resource_usage'] = usage
    base.append_event(out, plan, row, status, **details)
    return stop


def resource_pilot(out, *, history_roots, history_scope_note,
                   seed=960001, run_id=96000001, probe=None, executor=bounded_execute,
                   timer_path=Path('/usr/bin/time')):
    """One explicitly authorized resource qualification, never a scientific family."""
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Pilot output already exists; never retry or overwrite')
    verify_drive_mount(out)
    row = base.build_rows('principal', seed_base=seed, run_base=run_id)[0]
    for family in frozen_rows().values():
        if any(r['seed'] == seed or r['run'] == run_id for r in family):
            raise ValueError('Pilot RNG overlaps frozen scientific identities')
    history = history_check({'pilot': [row]}, history_roots)
    provenance = inspect_pin()
    timer = Path(timer_path)
    timer_hash = base.sha256(timer)
    if any(k.startswith('LD_') for k in os.environ):
        raise ValueError('Remove dynamic-loader environment overrides before pilot')
    policy = {'timeout_s': 120, 'row_bytes': 16 * MIB, 'address_space_bytes': 512 * MIB,
              'host_start_bytes': GIB, 'wsl_start_bytes': GIB, 'live_memory_floor_bytes': 512 * MIB}
    probe = probe or (lambda: resource_snapshot(out, '/mnt/c'))
    check = admission(policy, probe(), 1)
    if not check['admitted']:
        return {'pilot_status': 'not_admitted', 'execution_started': False, 'admission': check}
    raw, logs = out / 'raw', out / 'logs'
    command = [provenance['binary']] + [f'--{k}={v}' for k, v in row['options'].items()] + [f'--outDir={raw}']
    measured_command = [str(timer), '-v', '-o', str(logs / 'time-v.log'), '--', *command]
    manifest = {'schema': 'revision06-resource-pilot-v1', 'created_utc': base.utc(),
                'purpose': 'One resource-only principal DL/direct-composite qualification; never pooled',
                'row': row, 'policy': policy, 'provenance': provenance, 'admission': check,
                'command': measured_command, 'timer_sha256': timer_hash,
                'script_sha256': base.sha256(__file__), 'history': history,
                'history_scope': {'roots': [str(Path(p).resolve()) for p in history_roots],
                                  'note': history_scope_note, 'global_uniqueness_verified': False}}
    manifest['manifest_sha256'] = base.digest(manifest)
    out.mkdir(parents=True, exist_ok=False)
    base.write_json_new(out / 'resource_pilot.json', manifest)
    raw.mkdir()
    logs.mkdir()
    result = {'manifest_sha256': manifest['manifest_sha256'], 'seed': seed, 'run': run_id,
              'statistics': None, 'scientific_campaign_rows_completed': 0,
              'execution_started': False, 'pilot_status': 'not_started'}
    usage, started = {}, time.monotonic()
    try:
        # Recheck just before process entry; no reuse of a pre-preparation sample.
        final_check = admission(policy, probe(), 1)
        result['final_admission'] = final_check
        if final_check['admitted']:
            result['execution_started'] = True
            rc = executor(measured_command, provenance['source_root'], logs / 'stdout.log',
                          logs / 'stderr.log', 120, policy=policy, probe=probe, raw=raw, usage=usage)
            result['returncode'] = rc
            result['pilot_status'] = 'process_succeeded_unanalyzed' if rc == 0 else 'failed'
            if rc == 0:
                if not all((raw / name).is_file() for name in base.RAW_FILES):
                    raise ValueError('Required pilot raw output absent')
                if directory_bytes(raw, logs) > policy['row_bytes']:
                    raise OperationalStop('Pilot output exceeded storage cap')
        else:
            result['pilot_status'] = 'not_admitted'
    except subprocess.TimeoutExpired as exc:
        result.update(pilot_status='timeout', error=str(exc))
    except (KeyboardInterrupt, OperationalStop) as exc:
        result.update(pilot_status='interrupted', error=str(exc))
    except (OSError, ValueError, KeyError) as exc:
        result.update(pilot_status='failed', error=str(exc))
    result['elapsed_wall_s'] = time.monotonic() - started
    result['sampled_time_wrapper_usage'] = usage
    result['raw_sha256'] = {p.relative_to(raw).as_posix(): base.sha256(p) for p in raw.rglob('*') if p.is_file()}
    result['log_sha256'] = {p.relative_to(out).as_posix(): base.sha256(p) for p in logs.rglob('*') if p.is_file()}
    timing = logs / 'time-v.log'
    if timing.exists():
        timing_text = timing.read_text(encoding='utf-8')
        rss = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', timing_text)
        result['gnu_time_maximum_rss_bytes'] = int(rss.group(1)) * 1024 if rss else None
    base.write_json_new(out / 'resource_pilot_result.json', result)
    return result


def run(out, *, profiles=('principal', 'channel-sensitivity'), max_rows=20, wall_seconds=7200,
        recover_interrupted=False, orphan_confirmed=False, probe=None, executor=bounded_execute):
    if (isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= 680
            or not math.isfinite(wall_seconds) or wall_seconds <= 0):
        raise ValueError('Require finite positive wall budget and 1..680 row starts')
    if not profiles or len(set(profiles)) != len(profiles) or not set(profiles) <= set(ORDER):
        raise ValueError('Only complete focused profiles may be scheduled')
    if any(k.startswith('LD_') for k in os.environ):
        raise ValueError('Remove dynamic-loader environment overrides before execution')
    out, started, starts = Path(out).resolve(), time.monotonic(), 0
    with base.campaign_lock(out):
        manifest, plans = load(out)
        probe = probe or (lambda: resource_snapshot(out, manifest['backing_store']))
        for family in ORDER:
            if family not in profiles:
                continue
            location, plan, policy = out / family, plans[family], manifest['policies'][family]
            with base.campaign_lock(location):
                states = base.read_ledger(location, plan)
                running = [r for r in plan['rows'] if states[r['row_id']]['status'] == 'running']
                if running and not (recover_interrupted and orphan_confirmed):
                    raise ValueError('Crash-left running row: confirm no orphan, then --recover-interrupted --orphan-confirmed; NEVER retry')
                for row in running:
                    base.append_event(location, plan, row, 'interrupted', error='Explicit orphan-confirmed recovery; never retry')
                    states[row['row_id']]['status'] = 'interrupted'
                for row in plan['rows']:
                    if states[row['row_id']]['status'] != 'planned':
                        continue
                    reason = None
                    if (out / 'STOP').exists():
                        reason = 'STOP exists; pending rows untouched'
                    elif starts >= max_rows:
                        reason = 'Invocation row-start budget reached; pending rows untouched'
                    elif wall_seconds - (time.monotonic() - started) < policy['timeout_s'] + 60:
                        reason = 'Insufficient invocation time for a full row timeout + 60s overhead'
                    if reason:
                        return {**report(out, plans), 'pause_reason': reason, 'rows_started_this_invocation': starts}
                    base.verify_inputs(plan)
                    if base.sha256(PIN_ROOT / 'em_bridge_build_pin_v1.json') != PIN_SHA:
                        raise ValueError('Original build pin changed')
                    verify_libraries(plan['provenance']['pin'])
                    pending = sum(e['status'] == 'planned' for e in states.values())
                    check = admission(policy, probe(), pending)
                    if not check['admitted']:
                        return {**report(out, plans), 'admission': check, 'rows_started_this_invocation': starts}
                    # Also recheck STOP and time after provenance/resource probes.
                    if (out / 'STOP').exists() or wall_seconds - (time.monotonic() - started) < policy['timeout_s'] + 60:
                        return {**report(out, plans), 'pause_reason': 'Stop/time gate after probes', 'rows_started_this_invocation': starts}
                    starts += 1
                    stopped = execute_row(location, plan, row, policy, executor, probe, check)
                    states = base.read_ledger(location, plan)
                    if stopped:
                        return {**report(out, plans), 'pause_reason': 'Operator/live resource interruption; no retry',
                                'rows_started_this_invocation': starts}
    return {**report(out, plans), 'rows_started_this_invocation': starts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--history-root', required=True, action='append', type=Path)
    p.add_argument('--prior-plan', default=[], action='append', type=Path)
    p.add_argument('--seed-base', type=int, default=SEED_BASE)
    p.add_argument('--run-base', type=int, default=RUN_BASE)
    p.add_argument('--backing-store', type=Path, default=Path('/mnt/c'))
    p.add_argument('--history-scope-note', default='Only supplied roots inspected; uniqueness outside them is unverified')
    p = sub.add_parser('resource-pilot', help='One explicitly authorized capped resource-only row; not campaign execution')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--history-root', required=True, action='append', type=Path)
    p.add_argument('--history-scope-note', required=True)
    p.add_argument('--seed', type=int, default=960001)
    p.add_argument('--run-id', type=int, default=96000001)
    p.add_argument('--execute', action='store_true')
    p = sub.add_parser('inspect', help='Read pin/help/resources; never simulate or write plans')
    p.add_argument('--out', type=Path, default=Path('/mnt/w/Velocity-Connect-Revision06'))
    p.add_argument('--backing-store', type=Path, default=Path('/mnt/c'))
    for action in ('status', 'admit', 'run'):
        p = sub.add_parser(action)
        p.add_argument('--out', type=Path, required=True)
        if action in ('admit', 'run'):
            p.add_argument('--profiles', nargs='+', choices=ORDER, default=list(ORDER[:2]))
        if action == 'run':
            p.add_argument('--execute', action='store_true', help='Explicit simulation opt-in; required')
            p.add_argument('--max-rows', type=int, default=20)
            p.add_argument('--wall-seconds', type=float, default=7200)
            p.add_argument('--recover-interrupted', action='store_true')
            p.add_argument('--orphan-confirmed', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'prepare':
            result = prepare(args.out, history_roots=args.history_root, prior_plans=args.prior_plan,
                             seed_base=args.seed_base, run_base=args.run_base, backing_store=args.backing_store,
                             history_scope_note=args.history_scope_note)
        elif args.action == 'resource-pilot':
            if not args.execute:
                raise ValueError('Resource pilot requires explicit --execute authorization')
            result = resource_pilot(args.out, history_roots=args.history_root, history_scope_note=args.history_scope_note,
                                    seed=args.seed, run_id=args.run_id)
        elif args.action == 'inspect':
            pin = inspect_pin()
            snap = resource_snapshot(args.out, args.backing_store)
            result = {'binary_sha256': pin['binary_sha256'], 'source_bundle_sha256': pin['source_bundle_sha256'],
                      'source_files_verified': len(pin['source_sha256']),
                      'libraries_verified': len(pin['pin']['library_sha256']),
                      'families': {p: admission(POLICY[p], snap, COUNTS[p]) for p in ORDER}, 'execution_started': False}
        elif args.action == 'run':
            if not args.execute:
                raise ValueError('No execution without explicit --execute; use admit first')
            def interrupt(signum, frame):
                raise KeyboardInterrupt(f'Operator signal {signum}')
            previous = signal.signal(signal.SIGTERM, interrupt)
            try:
                result = run(args.out, profiles=tuple(args.profiles), max_rows=args.max_rows,
                             wall_seconds=args.wall_seconds, recover_interrupted=args.recover_interrupted,
                             orphan_confirmed=args.orphan_confirmed)
            finally:
                signal.signal(signal.SIGTERM, previous)
        else:
            manifest, plans = load(args.out)
            result = report(args.out, plans)
            if args.action == 'admit':
                snapshot = resource_snapshot(args.out, manifest['backing_store'])
                result['admission'] = {p: admission(POLICY[p], snapshot,
                    result['families'][p]['status_counts'].get('planned', 0)) for p in args.profiles}
        print(json.dumps(result, indent=2, allow_nan=False))
        if args.action == 'run':
            return 0 if all(result['families'][p]['campaign_status'] == 'succeeded' for p in args.profiles) else 2
        if args.action == 'admit':
            return 0 if all(check['admitted'] for check in result['admission'].values()) else 2
        if args.action == 'resource-pilot':
            return 0 if result['pilot_status'] == 'process_succeeded_unanalyzed' else 2
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'revision06 refused: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('revision06 interrupted between rows or during preparation; inspect retained state', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
