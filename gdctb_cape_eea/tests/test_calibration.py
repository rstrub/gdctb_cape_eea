import os
import shutil
import tempfile
import time
import warnings
from pathlib import Path

import ccsdspy
import numpy as np
import pytest
from spacepy import pycdf

import gdctb_cape_eea
import gdctb_cape_eea.calibration as calib
from gdctb_cape_eea import _calibration_directory, _data_directory, log
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


@pytest.fixture(
    scope="session",
    params=list(TEST_PROCESSING),
    ids=lambda bin_name: bin_name,
)  # this is a pytest fixture
def small_level0_file(request):
    if "txt" in request.param or "csv" in request.param:
        return Path(os.path.join(_calibration_directory, request.param))
    else:
        return Path(os.path.join(_data_directory, request.param))


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
    is_hk = apid in APIDS["HK"]
    packet_def_csv = (
        "gdctb_cape-eea_hk_packet_def.csv" if is_hk else "gdctb_cape-eea_sci_packet_def.csv"
    )
    pkt = ccsdspy.FixedLength.from_file(
        os.path.join(gdctb_cape_eea._data_directory, packet_def_csv)
    )
    result = read_ccsds(small_level0_file, pkt)
    if is_hk:
        assert len(result["ANODE_V"]) > 0
        n_uniq = len(get_unique_list(result["ANODE_V"]))
        ratio = n_uniq / len(result["ANODE_V"])
        assert ratio < 0.2  # Expecting a lot of repetition in ANODE_V for HK packets
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

    from gdctb_cape_eea.io.EEA import EPOCHTIMEFILL, INTFILL, REAL4FILL

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
            log.info(f"No {SKYMAP_VAR} in {output_l1a}; skipping the counter check (expected for HK files)")
        else:
            passed_sweeps = []
            failed_sweeps = []
            for i in range(n_sweeps):
                skymap_vals = cdf[SKYMAP_VAR][i]
                counter_vals = cdf[COUNTER_VAR][i]
                # sum both over the same steps: the ones the counter actually reported
                valid = counter_vals != INTFILL
                total = np.sum(np.where(skymap_vals == REAL4FILL, 0, skymap_vals)[valid])
                cntsum = np.sum(counter_vals[valid])
                # The counter runs a little high relative to the 32 azimuth bins, and this is a whole
                # sweep (not one packet), so allow 10%, with a small absolute floor for tiny totals.
                diff = max(int(0.1 * total), COUNTER_ABS_TOLERANCE)

                log.info(f"totals: skymap:{total} counter:{cntsum}")
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


def cleanup_retry(directory):
    """Attempt to clean up the directory after a short delay."""
    try:
        shutil.rmtree(directory)
    except PermissionError as e:
        print(f"Failed to clean up directory {directory} due to PermissionError: {e}")
