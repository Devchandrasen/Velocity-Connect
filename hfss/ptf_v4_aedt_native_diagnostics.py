# Native AEDT diagnostics for the active PTF-V4 design.

import ScriptEnv
import os
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(
    ROOT, "Velocity_Connect_PTF_V4_FourPort_Feedthrough_native_diagnostics.log"
)


def log(value):
    handle = open(LOG_PATH, "a")
    try:
        handle.write(str(value) + "\n")
    finally:
        handle.close()


def safe(label, callback):
    try:
        value = callback()
        log(label + ": " + repr(value))
    except Exception:
        log(label + " FAILED: " + traceback.format_exc())


if os.path.exists(LOG_PATH):
    os.remove(LOG_PATH)

ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")
project = oDesktop.GetActiveProject()
design = project.GetActiveDesign()
project_name = project.GetName()
design_name = design.GetName()
log("Project: " + project_name)
log("Design: " + design_name)

boundary = design.GetModule("BoundarySetup")
analysis = design.GetModule("AnalysisSetup")
editor = design.SetActiveEditor("3D Modeler")
safe("Excitations", lambda: boundary.GetExcitations())
safe("Boundaries", lambda: boundary.GetBoundaries())
safe("Setups", lambda: analysis.GetSetups())
safe("Sweeps", lambda: analysis.GetSweeps("Setup_PTF_V4"))
safe("Objects", lambda: editor.GetObjectsInGroup("Solids"))
safe("Messages", lambda: oDesktop.GetMessages(project_name, design_name, 0))
log("Diagnostics complete")
