"""SYNTHETIC launcher tests only. Never execute the ns-3/HFSS binaries."""
import csv
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import run_vehcom_revision06 as rev
from scripts import run_vehcom_validation as base


def good_resources():
    return {'host_available_bytes': 10 * rev.GIB, 'wsl_available_bytes': 10 * rev.GIB,
            'output_free_bytes': 200 * rev.GIB, 'backing_free_bytes': 10 * rev.GIB}


def fixture_output(raw, row):
    o = row['options']
    duration = o['appStop'] - o['appStart']
    metrics = {k: 0 for k in base.METRICS}
    metrics.update(tx_pkts=10, rx_pkts=1, pdr=.1, jain_fairness=1,
                   throughput_mbps=(o['appPktSize'] - 12) * 8 / duration / 1e6)
    data = {**{v: o[k] for k, v in base.CSV_CONTROL.items()}, **metrics}
    with (raw / 'single_run.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(data))
        writer.writeheader()
        writer.writerow(data)
    # Other files are fixture-only markers; full scientific analysis must refuse
    # them. They suffice for the launcher's existence/hash contract, not statistics.
    for name in base.RAW_FILES[1:]:
        (raw / name).write_text('SYNTHETIC FIXTURE ONLY\n')


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    pin_root = tmp_path / 'fake-pin'
    pin_root.mkdir()
    binary = pin_root / 'NEVER-EXECUTE'
    binary.write_bytes(b'SYNTHETIC FIXTURE ONLY')
    source = pin_root / 'hsr_velocity_connect.cc'
    source.write_text('// fixture')
    library = pin_root / 'fixture-library.so'
    library.write_bytes(b'fixture')
    sources = {source.name: base.sha256(source)}
    pin = {'library_sha256': {str(library): base.sha256(library)}}
    pin_file = pin_root / 'em_bridge_build_pin_v1.json'
    pin_file.write_text(json.dumps(pin))
    provenance = {'binary': str(binary), 'binary_sha256': base.sha256(binary),
                  'source_root': str(pin_root), 'source_sha256': sources,
                  'source_bundle_sha256': base.digest(sources), 'pin': pin,
                  'supported_options': list(base.build_rows()[0]['options']) + ['outDir']}
    monkeypatch.setattr(rev, 'PIN_ROOT', pin_root)
    monkeypatch.setattr(rev, 'PIN_SHA', base.sha256(pin_file))
    monkeypatch.setattr(rev, 'inspect_pin', lambda **kwargs: provenance)
    evidence = pin_root / 'resource-evidence-fixture.json'
    evidence.write_text('SYNTHETIC FIXTURE ONLY')
    monkeypatch.setattr(rev, 'resource_qualification', lambda: {'path': str(evidence), 'sha256': base.sha256(evidence)})
    history = tmp_path / 'history'
    history.mkdir()
    (history / 'single_run.csv').write_text('seed,run\n1,171001\n')
    out = tmp_path / 'revision06'
    rev.prepare(out, history_roots=[history], backing_store=tmp_path)
    _, plans = rev.load(out)
    rows = {r['row_id']: r for plan in plans.values() for r in plan['rows']}
    calls = []

    def executor(command, cwd, stdout, stderr, timeout, **kwargs):
        raw = kwargs['raw']
        assert list(raw.iterdir()) == []
        assert raw != stdout.parent
        calls.append(raw.name)
        stdout.write_text('SYNTHETIC FIXTURE ONLY')
        stderr.write_text('')
        fixture_output(raw, rows[raw.name])
        return 0

    return out, plans, executor, calls


def test_exact_frozen_design_and_fresh_rng():
    rows = rev.frozen_rows()
    assert {p: len(r) for p, r in rows.items()} == rev.COUNTS
    expanded = base.build_rows('expanded', seed_base=rev.SEED_BASE, run_base=rev.RUN_BASE)
    assert expanded == rows['principal'] + rows['load'] + rows['channel-sensitivity']
    groups = base.Counter((r['cell_id'], r['treatment']) for r in expanded)
    assert set(v for k, v in groups.items() if k[0].startswith('principal')) == {40}
    assert set(v for k, v in groups.items() if not k[0].startswith('principal')) == {20}
    assert len({(r['seed'], r['run']) for r in expanded}) == 340
    assert min(r['seed'] for r in rows['channel-sensitivity']) == 862001
    assert min(r['run'] for r in rows['load']) == 86001001
    assert all(r['planned_active_km'] == pytest.approx(1) for r in expanded)


@pytest.mark.parametrize('field', ['host_available_bytes', 'wsl_available_bytes',
                                  'output_free_bytes', 'backing_free_bytes'])
@pytest.mark.parametrize('bad', [0, None, float('nan')])
def test_admission_fails_closed(field, bad):
    snapshot = good_resources()
    snapshot[field] = bad
    assert not rev.admission(rev.POLICY['principal'], snapshot, 160)['admitted']


def test_current_resources_block_even_with_w_storage():
    snapshot = good_resources()
    snapshot.update(host_available_bytes=int(1.1 * rev.GIB), output_free_bytes=int(167.7 * rev.GIB),
                    backing_free_bytes=int(6.4 * rev.GIB))
    for p in rev.ORDER:
        check = rev.admission(rev.POLICY[p], snapshot, rev.COUNTS[p])
        assert not check['admitted']
        assert any('host_available_bytes' in x for x in check['reasons'])


def test_preparation_only_and_no_overwrite(prepared):
    out, plans, _, calls = prepared
    assert not calls
    assert rev.report(out, plans)['status_counts'] == {'planned': 680}
    assert not (out / 'principal' / 'raw').exists()
    with pytest.raises(ValueError, match='already exists'):
        rev.prepare(out, history_roots=[])
    m, _ = rev.load(out)
    assert m['history'][0]['identities'] == 1
    assert len(m['runtime_sha256']) == 5
    assert m['history_scope']['global_uniqueness_verified'] is False
    assert m['history_scope']['roots']


@pytest.mark.parametrize('seed,run', [(860001, 1), (1, 86000001)])
def test_history_rejects_either_seed_or_run_overlap(tmp_path, seed, run):
    (tmp_path / 'single_run.csv').write_text(f'seed,run\n{seed},{run}\n')
    with pytest.raises(ValueError, match='overlap'):
        rev.history_check(rev.frozen_rows(), [tmp_path])


def test_empty_history_refused(tmp_path):
    with pytest.raises(ValueError, match='No historical'):
        rev.history_check(rev.frozen_rows(), [tmp_path])


def test_aborted_legacy_csv_reserves_entire_declared_design(tmp_path):
    config = {'scenarios': ['composite', 'repeater'], 'speeds_kmph': [300, 500],
              'distances_m': [0], 'num_ues_values': [1], 'seeds': [101, 102], 'run_base': 180000}
    config_file = tmp_path / 'campaign_config.json'
    config_file.write_text(json.dumps(config))
    raw = tmp_path / 'raw/interrupted'
    raw.mkdir(parents=True)
    (raw / 'single_run.csv').write_text('')
    history = rev.history_check(rev.frozen_rows(), [tmp_path])
    fallback = next(x for x in history if 'malformed_result_retained' in x)
    assert fallback['identities'] == 8
    assert fallback['identity_source'] == str(config_file)
    config['run_base'] = rev.RUN_BASE - 7
    config_file.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='overlap'):
        rev.history_check(rev.frozen_rows(), [tmp_path])


def test_malformed_history_without_config_is_not_skipped(tmp_path):
    (tmp_path / 'single_run.csv').write_text('')
    with pytest.raises(ValueError, match='without declared identity fallback'):
        rev.history_check(rev.frozen_rows(), [tmp_path])


def test_pending_stop_resource_time_gates_do_not_touch_ledger(prepared):
    out, plans, executor, calls = prepared
    ledger = out / 'principal/ledger.jsonl'
    before = ledger.read_bytes()
    (out / 'STOP').touch()
    result = rev.run(out, executor=executor, probe=good_resources)
    assert 'STOP' in result['pause_reason']
    (out / 'STOP').rename(out / 'STOP-acknowledged-fixture')
    result = rev.run(out, executor=executor, probe=good_resources, wall_seconds=1800)
    assert 'time' in result['pause_reason']
    result = rev.run(out, executor=executor, probe=lambda: {**good_resources(), 'host_available_bytes': 1})
    assert not result['admission']['admitted']
    assert ledger.read_bytes() == before and not calls
    assert result['statistics'] is None


def test_serial_resume_bounded_starts_never_retries(prepared):
    out, plans, executor, calls = prepared
    result = rev.run(out, executor=executor, probe=good_resources, max_rows=2)
    assert result['status_counts'] == {'succeeded': 2, 'planned': 678}
    result = rev.run(out, executor=executor, probe=good_resources, max_rows=2)
    assert result['status_counts'] == {'succeeded': 4, 'planned': 676}
    assert len(calls) == len(set(calls)) == 4
    assert not result['all_680_succeeded'] and result['statistics'] is None


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'malformed'])
def test_failure_does_not_result_stop_or_retry(prepared, failure):
    out, plans, executor, calls = prepared
    attempts = []

    def fail_first(*args, **kwargs):
        attempts.append(kwargs['raw'].name)
        if len(attempts) == 1:
            if failure == 'timeout':
                raise subprocess.TimeoutExpired('FIXTURE', 1800)
            return 8 if failure == 'exit' else 0
        return executor(*args, **kwargs)

    result = rev.run(out, executor=fail_first, probe=good_resources, max_rows=4)
    assert len(attempts) == 4
    assert result['status_counts']['succeeded'] == 3
    rev.run(out, executor=fail_first, probe=good_resources, max_rows=2)
    assert len(attempts) == len(set(attempts)) == 6
    assert result['statistics'] is None


@pytest.mark.parametrize('exception', [KeyboardInterrupt, rev.OperationalStop])
def test_inflight_interrupt_is_terminal_not_retry(prepared, exception):
    out, plans, executor, calls = prepared

    def stop(*args, **kwargs):
        raise exception('fixture')

    result = rev.run(out, executor=stop, probe=good_resources)
    assert result['status_counts'] == {'interrupted': 1, 'planned': 679}
    rev.run(out, executor=executor, probe=good_resources, max_rows=1)
    assert calls == [plans['principal']['rows'][1]['row_id']]


def test_explicit_crash_recovery_does_not_relaunch_row(prepared):
    out, plans, executor, calls = prepared
    base.append_event(out / 'principal', plans['principal'], plans['principal']['rows'][0], 'running')
    with pytest.raises(ValueError, match='confirm no orphan'):
        rev.run(out, executor=executor, probe=good_resources, recover_interrupted=True)
    result = rev.run(out, executor=executor, probe=good_resources, max_rows=1,
                     recover_interrupted=True, orphan_confirmed=True)
    assert result['status_counts'] == {'interrupted': 1, 'succeeded': 1, 'planned': 678}


@pytest.mark.parametrize('target', ['runtime', 'library', 'binary', 'pin', 'source'])
def test_drift_refuses_before_simulation(prepared, target):
    out, plans, executor, calls = prepared
    paths = {'runtime': out / 'runtime/scripts/run_vehcom_validation.py',
             'library': rev.PIN_ROOT / 'fixture-library.so', 'binary': rev.PIN_ROOT / 'NEVER-EXECUTE',
             'pin': rev.PIN_ROOT / 'em_bridge_build_pin_v1.json', 'source': rev.PIN_ROOT / 'hsr_velocity_connect.cc'}
    paths[target].write_bytes(b'changed fixture')
    with pytest.raises(ValueError, match='changed'):
        rev.run(out, executor=executor, probe=good_resources)
    assert not calls


def test_full_family_only_is_not_680_complete(prepared):
    out, plans, executor, calls = prepared
    result = rev.run(out, executor=executor, probe=good_resources, profiles=('principal',), max_rows=160)
    assert result['families']['principal']['campaign_status'] == 'succeeded'
    assert result['status_counts'] == {'succeeded': 160, 'planned': 520}
    assert not result['all_680_succeeded'] and result['statistics'] is None
    rev.run(out, executor=lambda *a, **kw: pytest.fail('no rerun'), probe=good_resources,
            profiles=('principal',))


def test_run_cli_requires_opt_in(tmp_path):
    assert rev.main(['run', '--out', str(tmp_path)]) == 2


def test_concurrent_cooperating_runner_refused(prepared):
    out, _, executor, calls = prepared
    with base.campaign_lock(out):
        with pytest.raises(OSError):
            rev.run(out, executor=executor, probe=good_resources)
    assert not calls


def test_no_dynamic_loader_override(prepared, monkeypatch):
    out, _, executor, calls = prepared
    monkeypatch.setenv('LD_PRELOAD', '/fixture-only')
    with pytest.raises(ValueError, match='dynamic-loader'):
        rev.run(out, executor=executor, probe=good_resources)
    assert not calls


@pytest.mark.parametrize('case', ['success', 'timeout', 'denied'])
def test_resource_pilot_is_separate_capped_and_not_pooled(prepared, tmp_path, case):
    _, _, _, _ = prepared
    history = tmp_path / 'history'
    output = tmp_path / 'resource-pilot-fixture'
    timer = tmp_path / 'fake-time'
    timer.write_bytes(b'FIXTURE ONLY')
    calls = []

    def executor(command, cwd, stdout, stderr, timeout, **kwargs):
        calls.append(command)
        assert timeout == 120 and kwargs['policy']['address_space_bytes'] == 512 * rev.MIB
        assert kwargs['policy']['live_memory_floor_bytes'] == 512 * rev.MIB
        assert command[1:3] == ['-v', '-o']
        stdout.write_text('FIXTURE ONLY')
        stderr.write_text('')
        if case == 'timeout':
            raise subprocess.TimeoutExpired(command, 120)
        fixture_output(kwargs['raw'], base.build_rows('principal', seed_base=960001, run_base=96000001)[0])
        (stdout.parent / 'time-v.log').write_text('Maximum resident set size (kbytes): 32768\n')
        return 0

    probe = good_resources if case != 'denied' else lambda: {**good_resources(), 'host_available_bytes': rev.GIB - 1}
    result = rev.resource_pilot(output, history_roots=[history], history_scope_note='fixture-only scope',
        probe=probe, executor=executor, timer_path=timer)
    if case == 'denied':
        assert not calls and not output.exists() and not result['execution_started']
    else:
        assert len(calls) == 1 and result['scientific_campaign_rows_completed'] == 0
        assert result['statistics'] is None
        assert result['pilot_status'] == ('timeout' if case == 'timeout' else 'process_succeeded_unanalyzed')
        if case == 'success':
            assert result['gnu_time_maximum_rss_bytes'] == 32 * rev.MIB
        with pytest.raises(ValueError, match='already exists'):
            rev.resource_pilot(output, history_roots=[history], history_scope_note='fixture-only scope')


def test_resource_pilot_cannot_reuse_scientific_ids(tmp_path):
    with pytest.raises(ValueError, match='overlaps frozen'):
        rev.resource_pilot(tmp_path / 'pilot', history_roots=[], history_scope_note='fixture-only',
                           seed=rev.SEED_BASE, run_id=rev.RUN_BASE)


def test_resource_pilot_cli_requires_explicit_execute(tmp_path):
    assert rev.main(['resource-pilot', '--out', str(tmp_path), '--history-root', str(tmp_path),
                     '--history-scope-note', 'fixture-only']) == 2


def test_preparation_pin_inspection_uses_cached_help_without_any_process(tmp_path, monkeypatch):
    binary = tmp_path / 'hsr_velocity_connect'
    binary.write_bytes(b'NONEXECUTABLE FIXTURE')
    source = tmp_path / 'source/hsr_velocity_connect.cc'
    source.parent.mkdir()
    source.write_text('// fixture')
    sources = {source.name: base.sha256(source)}
    library = tmp_path / 'fake.so'
    library.write_bytes(b'fixture')
    pin = {'library_sha256': {str(library): base.sha256(library)}}
    pin_path = tmp_path / 'em_bridge_build_pin_v1.json'
    pin_path.write_text(json.dumps(pin))
    manifest = tmp_path / 'resource_pilot.json'
    manifest.write_text(json.dumps({'provenance': {'binary': str(binary), 'binary_sha256': base.sha256(binary),
        'source_sha256': sources, 'source_bundle_sha256': base.digest(sources), 'help': 'RECORDED FIXTURE HELP'}}))
    monkeypatch.setattr(rev, 'PIN_ROOT', tmp_path)
    monkeypatch.setattr(rev, 'PIN_SHA', base.sha256(pin_path))
    monkeypatch.setattr(rev, 'BINARY_SHA', base.sha256(binary))
    monkeypatch.setattr(rev, 'SOURCE_SHA', base.digest(sources))
    monkeypatch.setattr(rev, 'RESOURCE_EVIDENCE', tmp_path / 'resource_pilot_result.json')
    monkeypatch.setattr(rev, 'RESOURCE_PILOT_MANIFEST_SHA', base.sha256(manifest))
    monkeypatch.setattr(base, 'inspect_binary', lambda *a: pytest.fail('No PrintHelp during preparation'))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('No process during cached inspection'))
    result = rev.inspect_pin(execute_help=False)
    assert result['help'] == 'RECORDED FIXTURE HELP'
    assert 'without process launch' in result['help_evidence']


@pytest.mark.parametrize('max_rows,wall', [(0, 7200), (681, 7200), (1, float('inf')),
                                         (1, float('nan')), (True, 7200)])
def test_unbounded_invocations_rejected(prepared, max_rows, wall):
    out, _, executor, calls = prepared
    with pytest.raises(ValueError, match='finite positive'):
        rev.run(out, max_rows=max_rows, wall_seconds=wall, executor=executor, probe=good_resources)
    assert not calls


def test_default_window_cannot_launch_twelve_hour_load_row(prepared):
    out, _, executor, calls = prepared
    result = rev.run(out, profiles=('load',), executor=executor, probe=good_resources)
    assert not calls and 'time' in result['pause_reason']


def test_corrupt_ledger_never_repaired(prepared):
    out, _, executor, calls = prepared
    ledger = out / 'principal/ledger.jsonl'
    with ledger.open('a') as f:
        f.write('{truncated')
    before = ledger.read_bytes()
    with pytest.raises(ValueError, match='Invalid ledger'):
        rev.run(out, executor=executor, probe=good_resources)
    assert not calls and ledger.read_bytes() == before


def test_admission_snapshot_persisted_with_started_row(prepared):
    out, plans, executor, _ = prepared
    rev.run(out, executor=executor, probe=good_resources, max_rows=1)
    events = [json.loads(line) for line in (out / 'principal/ledger.jsonl').read_text().splitlines()]
    started = next(event for event in events if event['status'] == 'running')
    assert started['resource_admission']['admitted']
    assert started['revision06_limits']['address_space_bytes'] == 512 * rev.MIB


def test_cli_status_has_no_statistics_for_partially_executed_fixture(prepared, capsys):
    out, _, executor, _ = prepared
    rev.run(out, executor=executor, probe=good_resources, max_rows=1)
    assert rev.main(['status', '--out', str(out)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['statistics'] is None and result['status_counts']['succeeded'] == 1


@pytest.mark.parametrize('case', ['success', 'timeout', 'memory', 'disk', 'probe_failure',
                                  'invalid_memory', 'exit_race'])
def test_bounded_child_cleanup_and_os_limits_without_a_real_process(tmp_path, monkeypatch, case):
    kills, caps, launch = [], [], []
    monkeypatch.setattr(rev.signal, 'SIGKILL', 9, raising=False)
    def killpg(pid, sig):
        kills.append((pid, sig))
        if case == 'exit_race':
            raise ProcessLookupError('Fixture exited between poll and kill')

    monkeypatch.setattr(rev, 'os', SimpleNamespace(name='posix', environ={}, killpg=killpg))
    monkeypatch.setitem(sys.modules, 'resource', SimpleNamespace(RLIMIT_AS=1, RLIMIT_FSIZE=2,
        RLIMIT_CORE=3, setrlimit=lambda kind, value: caps.append((kind, value))))

    class FakeProcess:
        pid = 2147483000  # No actual process is looked up or signalled.
        done = False

        def poll(self):
            return 0 if self.done else None

        def wait(self, timeout=None):
            self.done = True
            return 0

    def popen(command, **kwargs):
        launch.append((command, kwargs))
        kwargs['preexec_fn']()
        return FakeProcess()

    monkeypatch.setattr(rev.subprocess, 'Popen', popen)
    raw = tmp_path / 'raw'
    raw.mkdir()
    logs = tmp_path / 'logs'
    logs.mkdir()

    def probe():
        if case == 'probe_failure':
            raise subprocess.TimeoutExpired('fixture-probe', 15)
        snap = good_resources()
        if case == 'memory':
            snap['host_available_bytes'] = rev.GIB - 1
        if case == 'disk':
            snap['output_free_bytes'] = rev.DISK_RESERVE - 1
        if case == 'invalid_memory':
            snap['host_available_bytes'] = float('nan')
        return snap

    def invoke():
        return rev.bounded_execute(['FIXTURE-DO-NOT-EXECUTE'], tmp_path,
            logs / 'stdout.log', logs / 'stderr.log', 0 if case in ('timeout', 'exit_race') else 30,
            policy=rev.POLICY['principal'], probe=probe, raw=raw)

    if case == 'success':
        assert invoke() == 0 and not kills
    else:
        with pytest.raises(subprocess.TimeoutExpired if case in ('timeout', 'exit_race') else rev.OperationalStop):
            invoke()
        assert kills == [(FakeProcess.pid, rev.signal.SIGKILL)]
    assert caps == [(1, (512 * rev.MIB,) * 2), (2, (16 * rev.MIB,) * 2), (3, (0, 0))]
    assert launch[0][1]['start_new_session'] is True
    assert launch[0][1]['env']['OMP_NUM_THREADS'] == '1'
