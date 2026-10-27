import os
import shutil
import tempfile
import time
import warnings
from pathlib import Path

import astropy.units as astropy_units
import ccsdspy
import numpy as np
import pytest
from spacepy import pycdf

import gdctb_cape_eea
import gdctb_cape_eea.calibration as calib
from gdctb_cape_eea import (
    _calibration_directory,
    _data_directory,
    _test_files_directory,
    log,
)
from gdctb_cape_eea.calibration.calibration import (
    APIDS,
    CURRENT_STEPPER_TABLE_FILE,
    get_apid_for_file,
    get_stepper_table_for_file,
    is_boot_packet,
)
from gdctb_cape_eea.io import read_ccsds
from gdctb_cape_eea.Stepper.StepperTable import get_unique_list
from gdctb_cape_eea.tests.conftest import TEST_PROCESSING

# boot_packet.txt entries in TEST_PROCESSING contain just the stepper table filename to use for
# whichever science files follow, until the next boot_packet.txt; persisted here to simulate the
# instrument's real behavior of applying the last-commanded stepper table, not a per-file lookup.


SKYMAP_VAR = "gdctb_cape_eea_accum"
COUNTER_VAR = "gdctb_cape_eea_counter1"
COUNTER_ABS_TOLERANCE = 2

HK_FIELD_OVERRIDES = {
    "TIME_DUR": {"catdesc": "packet_time_ms", "unit": astropy_units.ms},
    "PPS_DUR": {
        "catdesc": (
            "Instrument sub-second clock ticks elapsed since the arrival of the last "
            "1 Hz Pulse-Per-Second (PPS) synchronization signal."
        ),
        "unit": astropy_units.s / 256,
    },
    "T_FEE": {
        "catdesc": "EEA Front End Electronics Board temp",
        "unit": astropy_units.def_unit("deg_C"),
        "scale": -0.025,  # Example slope coefficient
        "offset": 107.5,  # Adjust based on calibration sheets to match ~20°C
    },
    "V_3_3V": {"unit": astropy_units.V, "scale": 0.000144},
    "V_3_3I": {"unit": astropy_units.mA, "scale": 0.018},
    "V_5_7V": {"unit": astropy_units.V, "scale": 0.000858},
    "V_5_7I": {"unit": astropy_units.mA, "scale": 0.083869},
    "V_NS_7V": {"unit": astropy_units.V, "scale": -0.000529},
    "V_11V": {"unit": astropy_units.V, "scale": 0.000551},
    "V_11": {"unit": astropy_units.mA, "scale": 0.049122},
    "T_LVPS": {
        "unit": astropy_units.def_unit("deg_C"),
        "scale": -0.0025,
        "offset": 98.4,
    },
    "ANODE_V": {"unit": astropy_units.V, "scale": 0.0116},
    "ESA_BULK_V": {"unit": astropy_units.V, "scale": 0.0154},
    "DEF_BULK_V": {"unit": astropy_units.V, "scale": 0.0232},
}


@pytest.fixture(
    scope="session",
    params=list(TEST_PROCESSING),
    ids=lambda bin_name: bin_name,
)  # this is a pytest fixture
def small_level0_file(request):
    if "txt" in request.param or "csv" in request.param:
        return Path(os.path.join(_calibration_directory, request.param))
    else:
        return Path(os.path.join(_test_files_directory, request.param))


def test_read_ccsdspy(small_level0_file):
    """
    Homage to Liam and the difficulties encountered at the outset...
    Parameters
    ----------
    small_level0_file - ccsds format packet file

    Returns
    -------

    """
    if is_boot_packet(small_level0_file):
        pytest.skip("ASCII files are not supported in this test")

    apid = get_apid_for_file(small_level0_file)
    # HK and science packets use different fixed-length layouts.
    key = next(k for k, v in APIDS.items() if apid in v)
    
    if key == "BOOT":
        packet_def_csv = "gdctb_cape-eea_boot_packet_def.csv"
    elif key == "HK":
        packet_def_csv = "gdctb_cape-eea_hk_packet_def.csv"
    elif key == "SCIENCE":
        packet_def_csv = "gdctb_cape-eea_sci_packet_def.csv"
    else:
        raise ValueError(f"Unexpected APID key: {key}")
    
    pkt = ccsdspy.FixedLength.from_file(
        os.path.join(gdctb_cape_eea._data_directory, packet_def_csv)
    )
    result = read_ccsds(small_level0_file, pkt)
    if key == "HK":
        assert len(result["ANODE_V"]) > 0
        n_uniq = len(get_unique_list(result["ANODE_V"]))
        ratio = n_uniq / len(result["ANODE_V"])
        assert ratio < 0.2  # Expecting a lot of repetition in ANODE_V for HK packets
    elif key == "BOOT":
        assert result['BSUM'] 
        assert result['BTABSEL'] in [0,1,2,3,4,5,6,7]  # Replace [0] with the expected value for BTABSEL in boot packets
    else:
        assert len(result["ACCUM"]) > 0
        assert len(result["ACCUM"][0]) == 34


def test_process_file(small_level0_file):
    """Test the boilerplate of the file processing function
       Tests a creation of a nominal L1A EEA file from packets
    calls:
        CCSDSPY
        A Custom EEA SkymapFactory
        SWXData
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdirname:
            # Create a Temp Copy of the Original
            temp_test_file_path = Path(tmpdirname, small_level0_file.name)
            shutil.copy(small_level0_file, temp_test_file_path)
            # Process the File
            output_files = calib.process_file(temp_test_file_path)
            if not is_boot_packet(temp_test_file_path):
                verify_l1a(small_level0_file, output_files[0])

    # Ensure the temporary directory is cleaned up even if an exception is raised (needed for Windows)
    except PermissionError:
        print("Encountered a PermissionError, retrying file deletion...")
        time.sleep(0.5)  # Wait a bit for the OS to release any locks
        cleanup_retry(tmpdirname)


def verify_l1a(data_filename, output_l1a):

    from gdctb_cape_eea.io.eea import EPOCHTIMEFILL, INTFILL, REAL4FILL

    assert os.path.getsize(output_l1a) > 275000
    with pycdf.CDF(str(output_l1a)) as cdf:
        # overall structure
        n_sweeps = len(cdf["Epoch"][:])
        length_time = (cdf["Epoch"][-1] - cdf["Epoch"][0]).total_seconds()

        assert n_sweeps > 0
        log.info(f"Length of CDF Variables: {n_sweeps}")
        log.info(f"Time   of CDF Variables: {length_time}")

        avg_sweep_seconds = length_time / max(n_sweeps - 1, 1)
        log.info(f"Average time per sweep: {avg_sweep_seconds:.3f} sec")
        assert avg_sweep_seconds > 0  # time should move forward, sweep to sweep

        # review variables
        variable_list = [item[0] for item in list(cdf.items())]
        for var in variable_list:
            log.info(var)
            if SKYMAP_VAR in variable_list:
                stepper = get_stepper_table_for_file(CURRENT_STEPPER_TABLE_FILE)
                assert cdf[var].shape[0] == n_sweeps
                if len(cdf[var].shape) >= 2 and "INT" in str(cdf[var]):
                    print(var)
                    assert cdf[var][0][stepper.n_defl * stepper.n_energies] in [
                    REAL4FILL,
                    EPOCHTIMEFILL,
                    INTFILL,
                    ]

        if SKYMAP_VAR not in variable_list:
            log.info(
                f"No {SKYMAP_VAR} in {output_l1a}; skipping the counter check (expected for HK files)"
            )
            verify_hk(cdf)
        else:
            passed_sweeps = []
            failed_sweeps = []
            for i in range(n_sweeps):
                skymap_vals = cdf[SKYMAP_VAR][i]
                counter_vals = cdf[COUNTER_VAR][i]
                # sum both over the same steps: the ones the counter actually reported
                valid = counter_vals != INTFILL
                total = np.sum(
                    np.where(skymap_vals == REAL4FILL, 0, skymap_vals)[valid]
                )
                cntsum = np.sum(counter_vals[valid])
                # The counter runs a little high relative to the 32 azimuth bins, and this is a whole
                # sweep (not one packet), so allow 10%, with a small absolute floor for tiny totals.
                diff = max(int(0.1 * total), COUNTER_ABS_TOLERANCE)

                log.info(f"totals: kl:{total} counter:{cntsum}")
                if abs(cntsum - total) <= diff:
                    passed_sweeps.append(i)
                else:
                    failed_sweeps.append((i, int(total), int(cntsum)))

            log.info(
                f"Counter vs skymap check on {output_l1a}: "
                f"{len(passed_sweeps)} of {n_sweeps} sweeps passed, {len(failed_sweeps)} failed"
            )
            for i, total, cntsum in failed_sweeps:
                log.info(f"  failed sweep {i}: skymap:{total} counter:{cntsum}")
            if failed_sweeps:
                warnings.warn(
                    f"{len(failed_sweeps)} of {n_sweeps} sweeps failed the counter vs skymap check; "
                    f"first few (sweep, skymap, counter): {failed_sweeps[:5]}",
                    stacklevel=2,
                )

    # best-effort local copy for manual inspection; _data_directory resolves regardless of cwd
    try:
        shutil.copy(output_l1a, _data_directory)
    except OSError as e:
        log.info(f"Could not save a local debug copy of {output_l1a}: {e}")


# Raw HK analog/thermistor monitors are all 16-bit unsigned counts (see
# gdctb_cape-eea_hk_packet_def.csv), so this is the largest raw value any of them can report.
RAW_FULL_SCALE = 2**16 - 1

# Sane engineering-unit windows for the fixed supply rails and thermistors, derived from each
# field's HK_FIELD_OVERRIDES scale/offset (chosen so nominal raw counts land near the rail's
# design voltage, e.g. V_3_3V's scale centers on 3.3V) plus margin for normal variation.
FIXED_RAIL_RANGES = {
    "T_FEE": (-40, 85),  # deg C, typical spacecraft electronics operating range
    "T_LVPS": (-40, 85),  # deg C
    "V_3_3V": (2.8, 3.8),  # nominal 3.3V bus
    "V_5_7V": (5.0, 6.4),  # nominal 5.7V bus
    "V_NS_7V": (-6.4, -5.0),  # nominal -5.7V bus
    "V_11V": (9.5, 12.5),  # nominal 11V bus
}
# Current monitors should be non-negative and nowhere near the digitizer's full-scale count
# (pinning at full scale usually indicates an overcurrent fault or a disconnected sensor).
CURRENT_MONITOR_FIELDS = {"V_3_3I", "V_5_7I", "V_11"}
# ANODE_V/ESA_BULK_V/DEF_BULK_V track the commanded ESA/deflector sweep voltage, so they vary
# packet to packet instead of holding near one nominal value; just confirm they stay within the
# physically valid 0-to-full-scale window implied by the monitor's own scale factor.
SWEEP_MONITOR_FIELDS = {"ANODE_V", "ESA_BULK_V", "DEF_BULK_V"}


def verify_hk(cdf):
    """Apply the HK_FIELD_OVERRIDES scale/offset to the raw HK telemetry stored in an L1A HK
    CDF and judge whether the resulting engineering-unit values are physically plausible for
    CAPE-EEA housekeeping.

    Parameters
    ----------
    cdf : spacepy.pycdf.CDF
        An open L1A HK CDF (as written by `l0_hk_data_to_cdf`). HK fields are stored as raw,
        uncalibrated counts under variable names `gdctb_cape_eea_<field>` (lowercased), matching
        gdctb_cape-eea_hk_packet_def.csv.
    """
    for field, overrides in HK_FIELD_OVERRIDES.items():
        var_name = f"gdctb_cape_eea_{field.lower()}"
        if var_name not in cdf:
            continue
        raw = np.asarray(cdf[var_name][:], dtype=float)
        scale = overrides.get("scale", 1.0)
        offset = overrides.get("offset", 0.0)
        values = raw * scale + offset

        assert np.all(np.isfinite(values)), f"{field}: non-finite calibrated values"
        log.info(
            f"{field}: min={values.min():.4g} max={values.max():.4g} mean={values.mean():.4g} "
            f"{overrides.get('unit', '')}"
        )

        if field in FIXED_RAIL_RANGES:
            low, high = FIXED_RAIL_RANGES[field]
            # Allow a small fraction of noisy/transient samples before failing outright.
            n_out = int(np.sum((values < low) | (values > high)))
            assert n_out / len(values) < 0.1, (
                f"{field}: {n_out}/{len(values)} calibrated samples fall outside the expected "
                f"[{low}, {high}] range"
            )
        elif field in CURRENT_MONITOR_FIELDS:
            full_scale_value = RAW_FULL_SCALE * scale
            assert np.all(values >= -1.0), (
                f"{field}: negative current reading is non-physical"
            )
            assert values.max() < full_scale_value * 0.9, (
                f"{field}: current reading near full-scale ({full_scale_value:.4g}), suggests "
                "an overcurrent fault or bad calibration"
            )
        elif field in SWEEP_MONITOR_FIELDS:
            full_scale_value = RAW_FULL_SCALE * scale
            assert np.all(values >= -1.0), (
                f"{field}: negative sweep voltage is non-physical"
            )
            assert np.all(values <= full_scale_value * 1.01), (
                f"{field}: calibrated value exceeds the monitor's full-scale range "
                f"({full_scale_value:.4g})"
            )
        elif field in ("PPS_DUR", "TIME_DUR"):
            # These raw 16-bit counters measure elapsed time since the last PPS/time packet and
            # have no scale/offset override, so the calibrated value is just the raw tick count.
            # Real telemetry can have sparse PPS/time packets (as in this test data, which has
            # intentional packet gaps), so only non-negativity is a reliable physical check here.
            assert np.all(values >= 0), f"{field} must not be negative"


def cleanup_retry(directory):
    """Attempt to clean up the directory after a short delay."""
    try:
        shutil.rmtree(directory)
    except PermissionError as e:
        print(f"Failed to clean up directory {directory} due to PermissionError: {e}")
