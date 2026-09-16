from copy import deepcopy
from hfss.audit_radiator_power import audit


def fixture():
    native = [{"active_terminal": f"Port{k}_T1", "accepted_power_w": 0.9,
               "incident_power_w": 1.0, "radiated_power_w": 0.81,
               "radiation_efficiency_ratio": 0.9} for k in (1, 2)]
    fields = [{"source": f"Port{k}", "radiated_power_far_field_integral_w": 0.809}
              for k in (1, 2)]
    return {"status": "complete", "solved": True, "antenna_parameters_center": native,
            "embedded_pattern_metrics": {"per_port": fields}}


def test_bounds_are_necessary_not_full_closure():
    result = audit(fixture(), "Converged : Yes\n")
    assert result["necessary_checks_pass"]
    assert not result["full_energy_closure_demonstrated"]
    assert not result["independent_solver_validation"]


def test_legacy_one_percent_allowance_cannot_admit_nonphysical_power():
    record = fixture()
    record["antenna_parameters_center"][0].update(
        radiated_power_w=0.905, radiation_efficiency_ratio=0.905 / 0.9,
        power_balance_within_one_percent=True, power_balance_strictly_physical=True)
    unchanged = deepcopy(record)
    result = audit(record, "Converged : Yes\n")
    assert not result["necessary_checks_pass"]
    assert result["ports"][0]["native_excess_percent"] > 0
    assert record == unchanged
    assert not result["values_clipped_or_renormalized"]


def test_missing_failed_nonfinite_or_unconverged_data_cannot_pass():
    assert not audit({}, "Converged : Yes\n")["necessary_checks_pass"]
    assert not audit(fixture(), "Converged : No\n")["necessary_checks_pass"]
    for value in (float("nan"), float("inf"), -0.5, 0):
        record = fixture()
        record["antenna_parameters_center"][0]["accepted_power_w"] = value
        assert not audit(record, "Converged : Yes\n")["necessary_checks_pass"]


def test_exported_ratio_is_checked_against_raw_power():
    record = fixture()
    record["antenna_parameters_center"][0]["radiation_efficiency_ratio"] = 0.99
    assert not audit(record, "Converged : Yes\n")["necessary_checks_pass"]


def test_duplicate_port_cannot_satisfy_two_port_gate():
    record = fixture()
    record["antenna_parameters_center"][1]["active_terminal"] = "Port1_T1"
    assert not audit(record, "Converged : Yes\n")["necessary_checks_pass"]
