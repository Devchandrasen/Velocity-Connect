# Solve and export the PTF-V5 physical-delay four-port HFSS project.

import ScriptEnv
import os
import traceback


SETUP_NAME = "Setup_PTF_V5"
SWEEP_NAME = "Sweep_n78"
ROOT = os.path.dirname(os.path.abspath(__file__))
TOUCHSTONE_PATH = os.path.join(
    ROOT,
    "results",
    "ptf_v5_delay25ps",
    "Velocity_Connect_PTF_V5_FourPort_Delay25ps",
    "PTF_V5_Delay25ps_FourPort_HFSS.s4p",
)
LOG_PATH = os.path.join(
    ROOT, "Velocity_Connect_PTF_V5_FourPort_Delay25ps_native_solve.log"
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
    validation = design.ValidateDesign()
    log("Validation result: %s" % validation)
    if not validation:
        raise RuntimeError("HFSS validation failed; solve was not started")

    project.Save()
    log("Solve started: " + SETUP_NAME)
    design.Analyze(SETUP_NAME)
    project.Save()
    log("Solve completed: " + SETUP_NAME)

    solution = design.GetModule("Solutions")
    solution.ExportNetworkData(
        "", [SETUP_NAME + ":" + SWEEP_NAME], 3, TOUCHSTONE_PATH,
        ["all"], False, 50, "S", -1, 1, 15, False, False, False,
    )
    if not os.path.exists(TOUCHSTONE_PATH):
        raise RuntimeError("ExportNetworkData did not create the Touchstone file")
    log("Touchstone exported: " + TOUCHSTONE_PATH)
    log("Touchstone bytes: %d" % os.path.getsize(TOUCHSTONE_PATH))
    messages = oDesktop.GetMessages(project_name, design_name, 0)
    for message in messages:
        log("MESSAGE " + str(message).replace("\r", " ").replace("\n", " "))
    log("PTF-V5 physical-delay solve/export complete")
    oDesktop.AddMessage(project_name, design_name, 0, "PTF-V5 physical-delay solve/export complete")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            log("FAILED")
            log(traceback.format_exc())
        except Exception:
            pass
        raise
