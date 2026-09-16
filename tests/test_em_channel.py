"""Reproducible bounded EM bridge tests; never rebuild or alter ns-3 dependencies.

Standalone: pytest tests/test_em_channel.py
Pinned smoke/pin: python3 tests/test_em_channel.py --ns3 PATH --work-dir NEW_PATH
The latter compiles serially from an isolated source snapshot and runs only
four 0.4s EM smokes plus one 0.4s scalar smoke. All operators are SYNTHETIC.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd, *, expected=0, timeout=180):
    p = subprocess.run([str(a) for a in args], cwd=cwd, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode != expected:
        raise RuntimeError(f"exit={p.returncode}, expected={expected}: {args}\n{p.stdout[-10000:]}")
    return p.stdout


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numerical(work):
    exe = work / "test_em_channel"
    run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1", f"-I{ROOT}",
         ROOT / "tests/test_em_channel.cc", "-o", exe], work)
    return run([exe, ROOT, work], work)


class NumericalTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("g++"), "standalone numerical test requires g++")
    def test_standalone_header(self):
        with tempfile.TemporaryDirectory(prefix="velocity-em-test-") as tmp:
            self.assertIn("PASS", numerical(Path(tmp)))


def pinned_validation(ns3, work):
    ns3, work = ns3.resolve(), work.resolve()
    work.mkdir(parents=True, exist_ok=False)  # no overwrite of an older evidence run
    source = work / "source"
    source.mkdir()
    sources = sorted(ROOT.glob("hsr_*.h")) + [ROOT / "hsr_velocity_connect.cc"]
    for p in sources:
        shutil.copyfile(p, source / p.name)
    hashes = {p.name: sha(source / p.name) for p in sources}
    expected = {"ns3": "d2add90b452d600cfb4859baed8e9ea633519447",
                "nr": "47a3adc263f773556eaadac5a5341458dbc61c47"}
    commits = {key: run(["git", "-C", path, "rev-parse", "HEAD"], work).strip()
               for key, path in (("ns3", ns3), ("nr", ns3 / "contrib/nr"))}
    if commits != expected:
        raise RuntimeError(f"not the required source pins: {commits}")
    logs = {"numerical": numerical(work)}
    libs = ["nr", "point-to-point", "internet", "applications", "mobility", "spectrum",
            "propagation", "antenna", "network", "core"]
    base = ["g++", "-std=c++20", "-O0", "-g0", "-fmax-errors=5",
            f"-I{source}", f"-I{ns3}/build/include", "-I/usr/include/eigen3"]
    link = [f"-L{ns3}/build/lib", f"-Wl,-rpath,{ns3}/build/lib"]
    link += [f"-lns3.48-{lib}-default" for lib in libs]
    commands = []
    for src, name in ((source / "hsr_velocity_connect.cc", "hsr_velocity_connect"),
                      (ROOT / "tests/test_em_channel_ns3.cc", "test_em_channel_ns3")):
        cmd = base + [str(src)] + link + ["-o", str(work / name)]
        commands.append(cmd)
        logs[f"compile_{name}"] = run(cmd, work)
    binary = work / "hsr_velocity_connect"
    fixture4 = ROOT / "fixtures/hfss/PTF_V4_Balanced_Cross.s4p"
    fixture5 = ROOT / "fixtures/hfss/PTF_V5_Delay25ps_Cross.s4p"
    operators = work / "synthetic_operators.csv"
    logs["ns3_psd"] = run([work / "test_em_channel_ns3", fixture4, operators], work)
    common = [binary, "--singleRun=1", "--speed=0", "--numUes=1", "--simTime=0.4",
              "--appStart=0.1", "--saturatingLoad=0", "--perUeOfferedMbps=1",
              "--nrRngStream=1000", "--seed=41", "--run=1"]
    treatments = [("v4-cross", fixture4, "cross", "downlink"),
                  ("v4-straight", fixture4, "straight", "downlink"),
                  ("v5-cross", fixture5, "cross", "downlink"),
                  ("v5-cross-ul", fixture5, "cross", "uplink")]
    evidence = {}
    gains = {}
    for name, fixture, mapping, direction in treatments:
        out = work / name
        cmd = common + ["--passiveModel=em_complex", f"--emTouchstone={fixture}",
                        f"--emOperators={operators}", f"--emMapping={mapping}",
                        f"--trafficDirection={direction}", f"--outDir={out}"]
        logs[name] = run(cmd, work, timeout=45)
        with (out / "single_run.csv").open() as f:
            result = next(csv.DictReader(f))
        assert result["effective_gnb_tx_power_dbm"] == result["gnb_tx_power_dbm"]
        assert result["effective_ue_tx_power_dbm"] == result["ue_tx_power_dbm"]
        assert math.isnan(float(result["eff_loss_db"]))
        assert result["channel_path"] == "em_absolute_static_siso"
        assert int(result["tx_pkts"]) > 0 and int(result["rx_pkts"]) > 0
        assert (out / "em_bridge_input.s4p").read_bytes() == fixture.read_bytes()
        assert (out / "em_bridge_operators.csv").read_bytes() == operators.read_bytes()
        with (out / "em_bridge_bands.csv").open() as f:
            bands = list(csv.DictReader(f))
        gains[name] = {}
        reciprocal = {}
        for b in bands:
            g, tx, rx = map(float, (b["power_gain"], b["first_tx_psd_w_hz"], b["first_rx_psd_w_hz"]))
            assert math.isclose(rx, tx*g, rel_tol=1e-12)
            key = float(b["frequency_hz"])
            reciprocal.setdefault(key, []).append(g)
            gains[name][key] = g
        for values in reciprocal.values():
            assert all(math.isclose(values[0], v, rel_tol=1e-12) for v in values)
        assert len(set(gains[name].values())) > 1
        with (out / "em_bridge_runtime.csv").open() as f:
            counters = next(csv.DictReader(f))
        assert int(counters["dl_channel_calls"]) > 0 and int(counters["ul_channel_calls"]) > 0
        evidence[name] = {"metrics": result, "runtime": counters, "command": list(map(str,cmd)),
                          "audit_path": str(out / "em_bridge_audit.md")}
        logs[name+"_overwrite_rejected"] = run(cmd, work, expected=2)
    for other in ("v4-straight", "v5-cross"):
        shared = gains["v4-cross"].keys() & gains[other].keys()
        assert shared and any(abs(gains["v4-cross"][f]-gains[other][f]) > 1e-15 for f in shared)
    # Candidate PSD effects, not forced packet KPI differences. Equality is legitimate.
    legacy = work / "scalar"
    logs["scalar"] = run(common + ["--passiveModel=component_budget", "--channelRngStream=100000",
                                   f"--outDir={legacy}"], work, timeout=45)
    with (legacy / "single_run.csv").open() as f:
        scalar = next(csv.DictReader(f))
    assert float(scalar["eff_loss_db"]) == 5 and float(scalar["effective_gnb_tx_power_dbm"]) == 35
    assert int(scalar["rx_pkts"]) > 0
    logs["missing_operators_rejected"] = run(common + ["--passiveModel=em_complex", f"--outDir={work}/missing"], work, expected=2)
    # Ensure the pin describes current authoritative files, not an intermediate snapshot.
    assert hashes == {p.name: sha(p) for p in sources}, "sources changed during build; rerun in a new directory"
    upstream_state = {}
    for name, path in (("ns3", ns3), ("nr", ns3 / "contrib/nr")):
        diff = run(["git", "-C", path, "diff", "--no-ext-diff"], work)
        upstream_state[name] = {"commit": commits[name], "root": str(path),
            "tracked_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
            "tracked_status": run(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"], work)}
    api_paths = ["contrib/nr/helper/nr-helper.cc", "contrib/nr/helper/nr-channel-helper.cc",
                 "contrib/nr/model/nr-spectrum-phy.cc", "src/spectrum/model/multi-model-spectrum-channel.cc",
                 "src/spectrum/model/spectrum-propagation-loss-model.h"]
    library_hashes = {str(p): sha(p) for p in sorted((ns3 / "build/lib").glob("libns3.48-*-default.so"))
                      if "-test-" not in p.name}
    pin = {"schema": "velocity-em-bridge-build-v1", "binary": {"path": str(binary), "sha256": sha(binary)},
           "synced_source_sha256": hashes, "source_snapshot": str(source),
           "authoritative_source_root": str(ROOT), "upstream": upstream_state,
           "compiler": {"path": shutil.which("g++"), "version": run(["g++", "--version"], work)},
           "headers": [str(ns3 / "build/include"), "/usr/include/eigen3", str(source)],
           "source_api_sha256": {p: sha(ns3 / p) for p in api_paths},
           "library_sha256": library_hashes, "compile_commands": commands,
           "fixture_sha256": {str(fixture4): sha(fixture4), str(fixture5): sha(fixture5)},
           "operators": {"path": str(operators), "sha256": sha(operators), "evidence": "synthetic"},
           "tests": logs, "bounded_smokes": evidence, "scalar_smoke": scalar,
           "physical_coupling_calibrated": False, "spatial_multiplexing": False,
           "common_channel_realizations_verified": False}
    pin_path = work / "em_bridge_build_pin_v1.json"
    with pin_path.open("x") as f:
        json.dump(pin, f, indent=2)
        f.write("\n")
    print(json.dumps({"status": "passed", "build_pin": str(pin_path), "binary": str(binary),
                      "smokes": list(evidence), "numerical": logs["numerical"].strip()}), flush=True)
    return pin_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ns3", type=Path)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    if args.ns3 and args.work_dir:
        pinned_validation(args.ns3, args.work_dir)
    elif args.ns3 or args.work_dir:
        parser.error("--ns3 and --work-dir must be supplied together")
    else:
        unittest.main(argv=[__file__])
