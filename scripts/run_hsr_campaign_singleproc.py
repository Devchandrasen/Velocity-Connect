
import argparse
import shutil
import subprocess
from pathlib import Path

import pandas as pd

SAFE_RUN_FALLBACKS = [10, 7, 8, 3, 1, 2, 4, 5, 6, 9, 11, 12, 13, 14, 15]

def unique_order(seq):
    out = []
    seen = set()
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def run_case(ns3_path, target, out_dir, scenario, speed, distance, num_ues,
             requested_run, saturating_load, per_ue_offered_mbps, verbose):
    out_dir = Path(out_dir)
    candidates = unique_order([requested_run] + SAFE_RUN_FALLBACKS)
    last_error = None

    for run_val in candidates:
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        sim_cmd = (
            f"{target} "
            f"--outDir={out_dir} "
            f"--scenario={scenario} "
            f"--speed={speed} "
            f"--distance={distance} "
            f"--numUes={num_ues} "
            f"--run={run_val} "
            f"--shadowing=0 "
            f"--nrScenario=UMi "
            f"--nrCondition=LOS "
            f"--nrChannelModel=ThreeGpp "
            f"--scheduler=ns3::NrMacSchedulerOfdmaRR "
            f"--appStart=0.5 "
            f"--enableSrs=0 "
            f"--saturatingLoad={1 if saturating_load else 0} "
            f"--perUeOfferedMbps={per_ue_offered_mbps} "
            f"--verbose={1 if verbose else 0}"
        )

        print(f"[case] scenario={scenario} speed={speed} distance={distance} numUes={num_ues} try_run={run_val}")

        try:
            subprocess.run([ns3_path, "run", sim_cmd], check=True)
            csv_path = out_dir / "single_result.csv"
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing result file: {csv_path}")

            df = pd.read_csv(csv_path)
            if len(df) != 1:
                raise RuntimeError(f"Expected one row in {csv_path}, found {len(df)}")

            row = df.iloc[0].to_dict()
            row["used_run"] = run_val
            return row

        except Exception as e:
            last_error = e
            print(f"[retry] failed with run={run_val}: {e}")

    raise RuntimeError(
        f"All retry runs failed for scenario={scenario}, speed={speed}, distance={distance}, numUes={num_ues}. "
        f"Last error: {last_error}"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns3", default="./ns3")
    ap.add_argument("--target", default="scratch/hsr_velocity_connect")
    ap.add_argument("--outdir", default="results_hsr")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    root = Path(args.outdir)
    raw_root = root / "raw"
    root.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)

    scenarios = ["metal", "composite", "repeater"]

    speed_rows = []
    requested_run = 1
    for scenario in scenarios:
        for speed in [0, 100, 200, 300, 400, 500]:
            row = run_case(
                args.ns3,
                args.target,
                raw_root / f"speed_{scenario}_{speed}",
                scenario=scenario,
                speed=speed,
                distance=500,
                num_ues=10,
                requested_run=requested_run,
                saturating_load=False,
                per_ue_offered_mbps=8.19,
                verbose=args.verbose,
            )
            speed_rows.append(row)
            requested_run += 1

    df_speed = pd.DataFrame(speed_rows)
    df_speed.to_csv(root / "sweep_speed.csv", index=False)

    distance_rows = []
    for scenario in scenarios:
        for distance in [100, 300, 500, 800, 1000, 1200, 1500]:
            row = run_case(
                args.ns3,
                args.target,
                raw_root / f"distance_{scenario}_{distance}",
                scenario=scenario,
                speed=300,
                distance=distance,
                num_ues=10,
                requested_run=requested_run,
                saturating_load=False,
                per_ue_offered_mbps=8.19,
                verbose=args.verbose,
            )
            distance_rows.append(row)
            requested_run += 1

    df_distance = pd.DataFrame(distance_rows)
    df_distance.to_csv(root / "sweep_distance.csv", index=False)

    scalability_rows = []
    for num_ues in [10, 20, 30, 40, 50]:
        row = run_case(
            args.ns3,
            args.target,
            raw_root / f"scalability_repeater_{num_ues}",
            scenario="repeater",
            speed=300,
            distance=500,
            num_ues=num_ues,
            requested_run=requested_run,
            saturating_load=False,
            per_ue_offered_mbps=8.19,
            verbose=args.verbose,
        )
        scalability_rows.append(row)
        requested_run += 1

    df_scal = pd.DataFrame(scalability_rows)
    df_scal.to_csv(root / "sweep_scalability.csv", index=False)

    print("Saved:")
    print(root / "sweep_speed.csv")
    print(root / "sweep_distance.csv")
    print(root / "sweep_scalability.csv")

if __name__ == "__main__":
    main()
