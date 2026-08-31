# Native AEDT builder for the physically delayed PTF-V5 four-port feedthrough.
#
# Channel B is 5.16 mm longer than Channel A.  The increment is derived from
# the mean 145.294 ps delay of the solved 30 mm PTF-V4 PTFE paths, giving an
# estimated 25.0 ps increment.  The V5 solve must measure the realized delay;
# the estimate is not used as the reported HFSS result.

import ScriptEnv
import os
import sys
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ptf_v4_aedt_native_build import (
    assign_wave_port,
    attributes,
    create_box,
    create_cylinder,
    face_at_z,
    subtract,
    unite,
)


PROJECT_PATH = os.path.join(ROOT, "Velocity_Connect_PTF_V5_FourPort_Delay25ps.aedt")
LOG_PATH = os.path.join(ROOT, "Velocity_Connect_PTF_V5_FourPort_Delay25ps_native_build.log")
DESIGN_NAME = "VC_PTF_V5_FourPortDelay25ps"
PROJECT_NAME = "Velocity_Connect_PTF_V5_FourPort_Delay25ps"
SETUP_NAME = "Setup_PTF_V5"
SWEEP_NAME = "Sweep_n78"
SHORT_LENGTH_MM = 30.0
EXTRA_LENGTH_MM = 5.16
LONG_LENGTH_MM = SHORT_LENGTH_MM + EXTRA_LENGTH_MM


def log(message):
    handle = open(LOG_PATH, "a")
    try:
        handle.write(str(message) + "\n")
        handle.flush()
    finally:
        handle.close()


def build_channel(editor, channel, x, bottom_z_mm, length_mm):
    z0 = "%gmm" % bottom_z_mm
    height = "%gmm" % length_mm
    inner = channel + "_Inner"
    dielectric = channel + "_PTFE"
    outer = channel + "_Outer"
    outer_tool = channel + "_OuterTool"
    collar_top = channel + "_RoofBondTop"
    collar_top_tool = channel + "_RoofBondTopTool"
    collar_bottom = channel + "_RoofBondBottom"
    collar_bottom_tool = channel + "_RoofBondBottomTool"

    create_cylinder(editor, inner, x, "0mm", z0, "0.5mm", height, "copper", False)
    create_cylinder(editor, dielectric, x, "0mm", z0, "1.675mm", height, "VC_PTFE", True)
    create_cylinder(editor, outer, x, "0mm", z0, "2mm", height, "copper", False)
    create_cylinder(editor, outer_tool, x, "0mm", z0, "1.675mm", height, "vacuum", True)
    subtract(editor, outer, outer_tool)

    create_cylinder(editor, collar_top, x, "0mm", "0.5mm", "3mm", "0.2mm", "copper", False)
    create_cylinder(editor, collar_top_tool, x, "0mm", "0.49mm", "1.675mm", "0.22mm", "vacuum", True)
    subtract(editor, collar_top, collar_top_tool)
    create_cylinder(editor, collar_bottom, x, "0mm", "-0.7mm", "3mm", "0.2mm", "copper", False)
    create_cylinder(editor, collar_bottom_tool, x, "0mm", "-0.71mm", "1.675mm", "0.22mm", "vacuum", True)
    subtract(editor, collar_bottom, collar_bottom_tool)
    unite(editor, [outer, collar_top, collar_bottom])

    top_face = face_at_z(editor, dielectric, 15.0)
    bottom_face = face_at_z(editor, dielectric, bottom_z_mm)
    x_value = float(x.replace("mm", ""))
    return top_face, bottom_face, x_value


def main():
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    log("PTF-V5 physical-delay native build started")

    ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")
    oDesktop.RestoreWindow()
    for existing_project in oDesktop.GetProjectList():
        if str(existing_project) == PROJECT_NAME:
            oDesktop.CloseProject(str(existing_project))
    oProject = oDesktop.NewProject()
    oProject.InsertDesign("HFSS", DESIGN_NAME, "DrivenModal", "")
    oDesign = oProject.SetActiveDesign(DESIGN_NAME)
    oEditor = oDesign.SetActiveEditor("3D Modeler")

    definition = oProject.GetDefinitionManager()
    if not definition.DoesMaterialExist("VC_PTFE"):
        definition.AddMaterial(
            [
                "NAME:VC_PTFE",
                "CoordinateSystemType:=", "Cartesian",
                ["NAME:AttachedData"],
                ["NAME:ModifierData"],
                "permittivity:=", "2.1",
                "conductivity:=", "0",
                "dielectric_loss_tangent:=", "0.0002",
            ]
        )

    create_box(
        oEditor, "AluminiumRoofCoupon", "-45mm", "-22.5mm", "-0.5mm",
        "90mm", "45mm", "1mm", "aluminum", False,
    )
    for index, x in enumerate(["-20mm", "20mm"]):
        tool = "RoofHoleTool%d" % (index + 1)
        create_cylinder(oEditor, tool, x, "0mm", "-1mm", "2mm", "2mm", "vacuum", True)
        subtract(oEditor, "AluminiumRoofCoupon", tool)

    boundary = oDesign.GetModule("BoundarySetup")
    channel_a = build_channel(
        oEditor, "ChannelA_D1_to_S2", "-20mm", -15.0, SHORT_LENGTH_MM
    )
    channel_b_bottom = 15.0 - LONG_LENGTH_MM
    channel_b = build_channel(
        oEditor, "ChannelB_D2_to_S1_Delay25ps", "20mm", channel_b_bottom, LONG_LENGTH_MM
    )
    port_contract = [
        ("Port1_DonorMinus", channel_a[0], channel_a[2], 15.0),
        ("Port2_DonorPlus", channel_b[0], channel_b[2], 15.0),
        ("Port3_ServiceMinus", channel_b[1], channel_b[2], channel_b_bottom),
        ("Port4_ServicePlus", channel_a[1], channel_a[2], -15.0),
    ]
    for port_name, face_id, x_value, z_value in port_contract:
        assign_wave_port(
            boundary,
            port_name,
            face_id,
            ["%gmm" % x_value, "0mm", "%gmm" % z_value],
            ["%gmm" % (x_value + 1.675), "0mm", "%gmm" % z_value],
        )

    analysis = oDesign.GetModule("AnalysisSetup")
    analysis.InsertSetup(
        "HfssDriven",
        [
            "NAME:" + SETUP_NAME,
            "SolveType:=", "Single",
            "Frequency:=", "3.55GHz",
            "MaxDeltaS:=", 0.005,
            "UseMatrixConv:=", False,
            "MaximumPasses:=", 10,
            "MinimumPasses:=", 3,
            "MinimumConvergedPasses:=", 2,
            "PercentRefinement:=", 20,
            "IsEnabled:=", True,
            "BasisOrder:=", 1,
            "DoLambdaRefine:=", True,
            "DoMaterialLambda:=", True,
            "SetLambdaTarget:=", False,
            "PortAccuracy:=", 4,
        ],
    )
    analysis.InsertFrequencySweep(
        SETUP_NAME,
        [
            "NAME:" + SWEEP_NAME,
            "IsEnabled:=", True,
            "RangeType:=", "LinearStep",
            "RangeStart:=", "3.3GHz",
            "RangeEnd:=", "3.8GHz",
            "RangeStep:=", "0.025GHz",
            "Type:=", "Interpolating",
            "SaveFields:=", False,
            "SaveRadFields:=", False,
            "InterpTolerance:=", 0.5,
            "InterpMaxSolns:=", 250,
            "InterpMinSolns:=", 0,
            "InterpMinSubranges:=", 1,
            "ExtrapToDC:=", False,
            "InterpUseS:=", True,
            "InterpUsePortImped:=", False,
            "InterpUsePropConst:=", True,
            "UseDerivativeConvergence:=", False,
            "EnforcePassivity:=", True,
            "PassivityErrorTolerance:=", 0.0001,
        ],
    )

    validation = oDesign.ValidateDesign()
    oProject.SaveAs(PROJECT_PATH, True)
    log("Validation result: %s" % validation)
    log("Project saved: %s" % PROJECT_PATH)
    log("Channel A physical length: %.3f mm" % SHORT_LENGTH_MM)
    log("Channel B physical length: %.3f mm" % LONG_LENGTH_MM)
    log("Physical length increment: %.3f mm" % EXTRA_LENGTH_MM)
    log("Port 3 service reference plane: %.3f mm" % channel_b_bottom)
    log("Port 4 service reference plane: -15.000 mm")
    log("PTF-V5 physical-delay native build complete")
    oDesktop.AddMessage(oProject.GetName(), DESIGN_NAME, 0, "PTF-V5 physical-delay build complete")


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
