# Export the completed PTF-V4 four-port HFSS sweep without re-running the solver.

import ScriptEnv
import os
import traceback


SETUP_NAME = "Setup_PTF_V4"
SWEEP_NAME = "Sweep_n78"
ROOT = os.path.dirname(os.path.abspath(__file__))
TOUCHSTONE_PATH = os.path.join(
    ROOT,
    "results",
    "ptf_v4_feedthrough",
    "Velocity_Connect_PTF_V4_FourPort_Feedthrough",
    "PTF_V4_FourPort_HFSS.s4p",
)
LOG_PATH = os.path.join(
    ROOT, "Velocity_Connect_PTF_V4_FourPort_Feedthrough_native_export.log"
)


def log(value):
    handle = open(LOG_PATH, "a")
    try:
        handle.write(str(value) + "\n")
        handle.flush()
    finally:
        handle.close()


def main():
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    output_folder = os.path.dirname(TOUCHSTONE_PATH)
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)
    if os.path.exists(TOUCHSTONE_PATH):
        os.remove(TOUCHSTONE_PATH)

    ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")
    project = oDesktop.GetActiveProject()
    design = project.GetActiveDesign()
    project_name = project.GetName()
    design_name = design.GetName()
    log("Project: " + project_name)
    log("Design: " + design_name)

    analysis = design.GetModule("AnalysisSetup")
    log("Setups: " + repr(analysis.GetSetups()))
    log("Sweeps: " + repr(analysis.GetSweeps(SETUP_NAME)))

    solution = design.GetModule("Solutions")
    solution.ExportNetworkData(
        "",
        [SETUP_NAME + ":" + SWEEP_NAME],
        3,
        TOUCHSTONE_PATH,
        ["all"],
        False,
        50,
        "S",
        -1,
        1,
        15,
        False,
        False,
        False,
    )
    if not os.path.exists(TOUCHSTONE_PATH):
        raise RuntimeError("HFSS returned from ExportNetworkData without creating the Touchstone file")
    log("Touchstone exported: " + TOUCHSTONE_PATH)
    log("Touchstone bytes: %d" % os.path.getsize(TOUCHSTONE_PATH))
    log("PTF-V4 existing-solution export complete")
    oDesktop.AddMessage(project_name, design_name, 0, "PTF-V4 completed sweep exported without re-solving")


try:
    main()
except Exception:
    try:
        log("FAILED")
        log(traceback.format_exc())
    except Exception:
        pass
    raise
