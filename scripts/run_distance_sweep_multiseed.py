import argparse
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

SCENARIOS = ["metal", "composite", "repeater"]
DISTANCES = [100, 300, 500, 800, 1000, 1200, 1500]

# Fixed candidate run IDs.
# We do not cherry-pick one run anymore. We collect multiple successful runs.
SEED_POOL = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
TARGET_SUCCESS = 5
TIMEOUT_SECONDS = 240

def ci95(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna().astype(float).to_numpy()
    n = len(vals)
    if n < 2:
        return float("nan")
    return 1.96 * float(np.std(vals, ddof=1)) / math.sqrt(n)

def run_case(ns3_path: str, target: str, out_dir: Path, scenario: str, distance: int, run_id: int):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sim_cmd = (
        f"{target} "
        f"--outDir={out_dir} "
        f"--scenario={scenario} "
        f"--speed=300 "
        f"--distance={distance} "
        f"--numUes=10 "
        f"--run={run_id} "
        f"--shadowing=0 "
        f"--nrScenario=UMi "
        f"--nrCondition=LOS "
        f"--nrChannelModel=ThreeGpp "
        f"--scheduler=ns3::NrMacSchedulerOfdmaRR "
        f"--appStart=0.5 "
        f"--enableSrs=0 "
        f"--saturatingLoad=0 "
        f"--perUeOfferedMbps=8.19 "
        f"--verbose=0"
    )

    try:
        result = subprocess.run(
            [ns3_path, "run", sim_cmd],
            check=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        csv_path = out_dir / "single_result.csv"
        if not csv_path.exists():
            return None, f"missing output csv: {csv_path}"

        df = pd.read_csv(csv_path)
        if len(df) != 1:
            return None, f"expected 1 row, found {len(df)} in {csv_path}"

        row = df.iloc[0].to_dict()
        row["seed_run"] = run_id
        row["distance_target_m"] = distance
        row["scenario_target"] = scenario
        return row, None

    except subprocess.TimeoutExpired:
        return None, f"timeout after {TIMEOUT_SECONDS}s"
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e))[-600:]
        return None, msg
    except Exception as e:
        return None, str(e)

def summarize_point(df_point: pd.DataFrame, scenario: str, distance: int, failed_runs):
    out = {
        "scenario": scenario,
        "distance_m": distance,
        "n_success": int(len(df_point)),
        "complete": int(len(df_point) >= TARGET_SUCCESS),
        "used_runs": "|".join(str(x) for x in df_point["seed_run"].tolist()) if len(df_point) else "",
        "failed_runs": "|".join(str(x) for x in failed_runs),
    }

    metric_cols = [
        "throughput_mbps",
        "pdr",
        "mean_lat_ms",
        "p50_lat_ms",
        "p95_lat_ms",
        "jain_fairness",
    ]

    for col in metric_cols:
        s = pd.to_numeric(df_point[col], errors="coerce") if len(df_point) else pd.Series(dtype=float)
        out[f"{col}_mean"] = float(s.dropna().mean()) if len(s.dropna()) else float("nan")
        out[f"{col}_ci95"] = ci95(s)

    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns3", default="./ns3")
    ap.add_argument("--target", default="scratch/hsr_velocity_connect")
    ap.add_argument("--outdir", default="results_distance_multiseed")
    args = ap.parse_args()

    root = Path(args.outdir)
    raw_root = root / "raw"
    root.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)

    raw_rows = []
    summary_rows = []
    failure_rows = []

    for scenario in SCENARIOS:
        for distance in DISTANCES:
            print(f"\n[point] scenario={scenario} distance={distance} m")
            successes = []
            failed_runs = []

            for run_id in SEED_POOL:
                point_dir = raw_root / f"{scenario}_{distance}m_run{run_id}"
                row, err = run_case(args.ns3, args.target, point_dir, scenario, distance, run_id)

                if row is not None:
                    successes.append(row)
                    print(f"  ok   run={run_id}  success_count={len(successes)}/{TARGET_SUCCESS}")
                else:
                    failed_runs.append(run_id)
                    failure_rows.append({
                        "scenario": scenario,
                        "distance_m": distance,
                        "seed_run": run_id,
                        "error": err,
                    })
                    print(f"  fail run={run_id}")

                if len(successes) >= TARGET_SUCCESS:
                    break

            df_point = pd.DataFrame(successes)
            if len(df_point):
                raw_rows.extend(successes)

            summary_rows.append(summarize_point(df_point, scenario, distance, failed_runs))

    df_raw = pd.DataFrame(raw_rows)
    df_summary = pd.DataFrame(summary_rows)
    df_fail = pd.DataFrame(failure_rows)

    raw_csv = root / "distance_raw.csv"
    summary_csv = root / "distance_summary.csv"
    fail_csv = root / "distance_failures.csv"

    df_raw.to_csv(raw_csv, index=False)
    df_summary.to_csv(summary_csv, index=False)
    df_fail.to_csv(fail_csv, index=False)

    print("\nSaved files:")
    print(raw_csv)
    print(summary_csv)
    print(fail_csv)

if __name__ == "__main__":
    main()
