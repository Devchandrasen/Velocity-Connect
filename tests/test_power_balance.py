import math
import random

import numpy as np
import pytest

from hfss.power_balance import assess_power_budget, integrate_far_field


def rows():
    return [{"theta": float(t), "phi": float(p), "etheta_re": math.sin(math.radians(t)),
             "etheta_im": 0.0, "ephi_re": 0.0, "ephi_im": 0.0}
            for t in np.linspace(0, 180, 181) for p in np.linspace(0, 360, 181)]


def record():
    return dict(incident_w=1.0, accepted_w=0.9, native_radiated_w=0.8,
                field_radiated_w=0.8, conductor_loss_w=0.08, dielectric_loss_w=0.02,
                native_context="port1:incident1V:raw", field_context="port1:incident1V:raw",
                loss_context="port1:incident1V:raw")


def test_coordinate_integral_is_order_independent_and_analytic():
    field = rows()
    expected = (8 * math.pi / 3) / (2 * 376.730313668)
    a = integrate_far_field(field, angle_unit="deg")
    random.Random(23).shuffle(field)
    b = integrate_far_field(field, angle_unit="deg")
    assert a == b
    assert a["radiated_power_w"] == pytest.approx(expected, rel=1e-7)


def test_coordinate_integral_units_agree():
    field = rows()
    degrees = integrate_far_field(field, angle_unit="deg")
    radians = [{**r, "theta": math.radians(r["theta"]), "phi": math.radians(r["phi"])} for r in field]
    assert integrate_far_field(radians, angle_unit="rad")["radiated_power_w"] == pytest.approx(degrees["radiated_power_w"])


@pytest.mark.parametrize("fault", ["duplicate", "missing", "nan", "partial"])
def test_invalid_field_grid_rejected(fault):
    field = rows()
    if fault == "duplicate": field[-1] = field[0]
    elif fault == "missing": field.pop()
    elif fault == "nan": field[0]["etheta_re"] = float("nan")
    else: field = [r for r in field if r["theta"] <= 90]
    with pytest.raises(ValueError): integrate_far_field(field, angle_unit="deg")


def test_power_conservation_passes_necessary_checks_only():
    result = assess_power_budget(record())
    assert result["necessary_checks_pass"]
    assert not result["mesh_independence_demonstrated"]


def test_loss_based_efficiency_cannot_hide_nonphysical_input_budget():
    r = record()
    r.update(native_radiated_w=0.92, field_radiated_w=0.92)
    result = assess_power_budget(r)
    assert result["loss_based_efficiency_diagnostic"] < 1
    assert result["native_efficiency"] > 1
    assert not result["necessary_checks_pass"]
    assert not result["values_clipped"]


@pytest.mark.parametrize("fault", ["missing_loss", "different_context", "false_export", "negative_loss"])
def test_incomplete_or_mixed_budget_rejected(fault):
    r = record()
    if fault == "missing_loss": r.pop("dielectric_loss_w")
    elif fault == "different_context": r["field_context"] = "modal1W"
    elif fault == "false_export": r["conductor_loss_w"] = False
    else: r["dielectric_loss_w"] = -0.01
    with pytest.raises(ValueError): assess_power_budget(r)


def test_power_export_refuses_low_memory_without_loading_solver(tmp_path, monkeypatch):
    import json
    from hfss import export_power_budget_revision06 as export
    source = tmp_path / "synthetic.aedt"
    source.write_text("synthetic test fixture; not an HFSS project")
    out = tmp_path / "audit"
    monkeypatch.setattr(export, "available_memory_gib", lambda: 1.5)
    monkeypatch.setattr("sys.argv", ["export", "--project", str(source), "--out", str(out)])
    assert export.main() == 3
    report = json.loads((out / "power_budget_report.json").read_text())
    assert report["status"] == "resource_admission_denied"
    assert report["source_project_unchanged"]
    assert report["results"] == [] and not report["solved_in_this_run"]


def test_explicit_field_export_reader_preserves_zero_imaginary_terms(tmp_path):
    from hfss.export_power_budget_revision06 import field_rows
    source = tmp_path / "fields.csv"
    source.write_text("Theta [deg],Phi [deg],re(rETheta) [V],im(rETheta) [V],re(rEPhi) [V],im(rEPhi) [V]\n90,0,1,0,0,0\n")
    values, unit = field_rows(source)
    assert unit == "deg" and values[0]["etheta_re"] == 1
    assert values[0]["ephi_im"] == 0


def test_missing_field_units_or_imaginary_column_is_not_filled(tmp_path):
    from hfss.export_power_budget_revision06 import field_rows
    source = tmp_path / "fields.csv"
    source.write_text("Theta,Phi,re(rETheta) [V]\n90,0,1\n")
    with pytest.raises(ValueError): field_rows(source)


def test_failed_hfss_export_cannot_be_misread_as_zero():
    from hfss.export_power_budget_revision06 import checked
    for bad in (False, None, float("nan"), float("inf")):
        with pytest.raises(RuntimeError): checked(bad)
    assert checked(0.0) == 0.0
    assert checked(-0.01) == -0.01  # Signed surface flux is not rectified.


def test_native_hfss_real_wrapper_and_millivolts_are_explicitly_converted(tmp_path):
    from hfss.export_power_budget_revision06 import field_rows
    expressions = ["re(rETheta)", "im(rETheta)", "re(rEPhi)", "im(rEPhi)"]
    header = ["Theta [deg]", "Phi [deg]"]
    for expression in expressions:
        header += [expression + " (Real) [mV]", expression + " (Imag) [mV]"]
    source = tmp_path / "fields.csv"
    source.write_text(",".join(header) + "\n90,0,1000,0,500,0,0,0,0,0\n")
    values, _ = field_rows(source)
    assert values[0]["etheta_re"] == 1.0
    assert values[0]["etheta_im"] == 0.5


def test_retained_native_failure_is_reproduced_without_accepting_physics():
    from pathlib import Path
    from hfss.replay_power_budget_revision06 import replay
    directory = Path(__file__).resolve().parents[1] / "fixtures/hfss/power_budget_revision06"
    result = replay(directory)
    assert result["status"] == "recorded_diagnostic_reproduced"
    assert not result["physical_acceptance"] and not result["solver_executed"]
    for row in result["results"]:
        budget = row["budget"]
        assert not budget["necessary_checks_pass"]
        assert 1.015 < budget["native_efficiency"] < 1.017
        assert 0.018 < budget["relative_input_closure_residual"] < 0.019
