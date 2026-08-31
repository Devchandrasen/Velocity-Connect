# Native AEDT script for the PTF-MIMO four-port roof feedthrough.
#
# Run this file from Ansys Electronics Desktop Student 2025 R2 using
# Automation > Run Script.  It deliberately avoids PyAEDT/gRPC so the project
# can still be generated when the external automation server is unavailable.

import ScriptEnv
import os
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.join(
    ROOT, "Velocity_Connect_PTF_V4_FourPort_Feedthrough.aedt"
)
LOG_PATH = os.path.join(
    ROOT, "Velocity_Connect_PTF_V4_FourPort_Feedthrough_native_build.log"
)
DESIGN_NAME = "VC_PTF_V4_FourPortFeedthrough"
SETUP_NAME = "Setup_PTF_V4"
SWEEP_NAME = "Sweep_n78"


def log(message):
    handle = open(LOG_PATH, "a")
    try:
        handle.write(str(message) + "\n")
        handle.flush()
    finally:
        handle.close()


def attributes(name, material, color, solve_inside):
    return [
        "NAME:Attributes",
        "Name:=", name,
        "Flags:=", "",
        "Color:=", color,
        "Transparency:=", 0,
        "PartCoordinateSystem:=", "Global",
        "UDMId:=", "",
        "MaterialValue:=", '"' + material + '"',
        "SurfaceMaterialValue:=", '""',
        "SolveInside:=", solve_inside,
        "ShellElement:=", False,
        "ShellElementThickness:=", "0mm",
        "IsMaterialEditable:=", True,
        "UseMaterialAppearance:=", False,
        "IsLightweight:=", False,
    ]


def create_cylinder(editor, name, x, y, z, radius, height, material, solve_inside):
    editor.CreateCylinder(
        [
            "NAME:CylinderParameters",
            "XCenter:=", x,
            "YCenter:=", y,
            "ZCenter:=", z,
            "Radius:=", radius,
            "Height:=", height,
            "WhichAxis:=", "Z",
            "NumSides:=", "0",
        ],
        attributes(name, material, "(224 126 30)", solve_inside),
    )


def create_box(editor, name, x, y, z, dx, dy, dz, material, solve_inside):
    editor.CreateBox(
        [
            "NAME:BoxParameters",
            "XPosition:=", x,
            "YPosition:=", y,
            "ZPosition:=", z,
            "XSize:=", dx,
            "YSize:=", dy,
            "ZSize:=", dz,
        ],
        attributes(name, material, "(160 160 164)", solve_inside),
    )


def subtract(editor, blank, tool):
    editor.Subtract(
        ["NAME:Selections", "Blank Parts:=", blank, "Tool Parts:=", tool],
        ["NAME:SubtractParameters", "KeepOriginals:=", False],
    )


def unite(editor, names):
    editor.Unite(
        ["NAME:Selections", "Selections:=", ",".join(names)],
        ["NAME:UniteParameters", "KeepOriginals:=", False],
    )


def face_at_z(editor, object_name, target_z):
    face_areas = []
    for face_id in editor.GetFaceIDs(object_name):
        try:
            face_areas.append((int(face_id), float(editor.GetFaceArea(face_id))))
        except Exception:
            pass
    if not face_areas:
        raise RuntimeError("Could not read faces for %s" % object_name)
    minimum_area = min(item[1] for item in face_areas)
    planar_candidates = [
        item[0] for item in face_areas if item[1] <= minimum_area * 1.01
    ]
    selected = None
    selected_error = 1.0e99
    for face_id in planar_candidates:
        try:
            center = editor.GetFaceCenter(face_id)
            error = abs(float(center[2]) - float(target_z))
            if error < selected_error:
                selected = int(face_id)
                selected_error = error
        except Exception:
            pass
    if selected is None or selected_error > 0.001:
        raise RuntimeError("Could not identify end face for %s at z=%s" % (object_name, target_z))
    return selected


def assign_wave_port(boundary, name, face_id, start, end):
    boundary.AssignWavePort(
        [
            "NAME:" + name,
            "Faces:=", [face_id],
            "NumModes:=", 1,
            "UseLineModeAlignment:=", False,
            "DoDeembed:=", False,
            "RenormalizeAllTerminals:=", True,
            [
                "NAME:Modes",
                [
                    "NAME:Mode1",
                    "ModeNum:=", 1,
                    "UseIntLine:=", True,
                    ["NAME:IntLine", "Start:=", start, "End:=", end],
                    "AlignmentGroup:=", 0,
                    "CharImp:=", "Zpi",
                    "RenormImp:=", "50ohm",
                ],
            ],
            "ShowReporterFilter:=", False,
            "ReporterFilter:=", [True],
            "UseAnalyticAlignment:=", False,
        ]
    )


def build_channel(editor, channel, x):
    z0 = "-15mm"
    inner = channel + "_Inner"
    dielectric = channel + "_PTFE"
    outer = channel + "_Outer"
    outer_tool = channel + "_OuterTool"
    collar_top = channel + "_RoofBondTop"
    collar_top_tool = channel + "_RoofBondTopTool"
    collar_bottom = channel + "_RoofBondBottom"
    collar_bottom_tool = channel + "_RoofBondBottomTool"

    create_cylinder(editor, inner, x, "0mm", z0, "0.5mm", "30mm", "copper", False)
    create_cylinder(editor, dielectric, x, "0mm", z0, "1.675mm", "30mm", "VC_PTFE", True)
    create_cylinder(editor, outer, x, "0mm", z0, "2mm", "30mm", "copper", False)
    create_cylinder(editor, outer_tool, x, "0mm", z0, "1.675mm", "30mm", "vacuum", True)
    subtract(editor, outer, outer_tool)

    # Conductive annular roof bonds sit immediately outside the roof volume.
    # They overlap the copper shield for uniting but only touch the aluminium
    # roof at z=+/-0.5 mm, eliminating dissimilar-material volume intersections.
    create_cylinder(editor, collar_top, x, "0mm", "0.5mm", "3mm", "0.2mm", "copper", False)
    create_cylinder(editor, collar_top_tool, x, "0mm", "0.49mm", "1.675mm", "0.22mm", "vacuum", True)
    subtract(editor, collar_top, collar_top_tool)
    create_cylinder(editor, collar_bottom, x, "0mm", "-0.7mm", "3mm", "0.2mm", "copper", False)
    create_cylinder(editor, collar_bottom_tool, x, "0mm", "-0.71mm", "1.675mm", "0.22mm", "vacuum", True)
    subtract(editor, collar_bottom, collar_bottom_tool)
    unite(editor, [outer, collar_top, collar_bottom])

    top_face = face_at_z(editor, dielectric, 15.0)
    bottom_face = face_at_z(editor, dielectric, -15.0)
    x_value = float(x.replace("mm", ""))
    return top_face, bottom_face, x_value


def main():
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    log("PTF-V4 native build started")

    ScriptEnv.Initialize("Ansoft.ElectronicsDesktop")
    oDesktop.RestoreWindow()
    for existing_project in oDesktop.GetProjectList():
        if str(existing_project) == "Velocity_Connect_PTF_V4_FourPort_Feedthrough":
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
        oEditor,
        "AluminiumRoofCoupon",
        "-45mm", "-22.5mm", "-0.5mm",
        "90mm", "45mm", "1mm",
        "aluminum", False,
    )
    for index, x in enumerate(["-20mm", "20mm"]):
        tool = "RoofHoleTool%d" % (index + 1)
        create_cylinder(oEditor, tool, x, "0mm", "-1mm", "2mm", "2mm", "vacuum", True)
        subtract(oEditor, "AluminiumRoofCoupon", tool)

    boundary = oDesign.GetModule("BoundarySetup")
    # Port order is the publication contract:
    # 1 D1-, 2 D2+, 3 S1-, 4 S2+.  Physical paths are S41 and S32.
    channel_a = build_channel(
        oEditor,
        "ChannelA_D1_to_S2",
        "-20mm",
    )
    channel_b = build_channel(
        oEditor,
        "ChannelB_D2_to_S1",
        "20mm",
    )
    port_contract = [
        ("Port1_DonorMinus", channel_a[0], channel_a[2], 15.0),
        ("Port2_DonorPlus", channel_b[0], channel_b[2], 15.0),
        ("Port3_ServiceMinus", channel_b[1], channel_b[2], -15.0),
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
    log("Port order: Port1_DonorMinus, Port2_DonorPlus, Port3_ServiceMinus, Port4_ServicePlus")
    log("Intended transfers: S(Port4,Port1) and S(Port3,Port2)")
    log("PTF-V4 native build complete")
    oDesktop.AddMessage(oProject.GetName(), DESIGN_NAME, 0, "PTF-V4 native build complete")


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
