"""
A module for all things calibration.
"""

from datetime import datetime, timezone, timedelta
import random
import os.path
import csv
import struct
from pathlib import Path
import sys
import ccsdspy
import numpy as np
import astropy.units as astropy_units
from astropy.timeseries import TimeSeries

from gdctb_cape_eea import log
from swxsoc.util.util import create_science_filename, parse_science_filename
from swxsoc.swxdata import SWXData
import gdctb_cape_eea
from gdctb_cape_eea.io import read_file
import gdctb_cape_eea.calibration as calib
from gdctb_cape_eea.io.EEA import EEA
from gdctb_cape_eea.SkymapFactory import skymap_factory
from gdctb_cape_eea.Stepper.StepperTable import StepperTable
from gdctb_cape_eea.util.time import ccsds_to_cdf_time
from gdctb_cape_eea.Stepper.StepperTable import get_unique_list

# cdflib -> spacepy
from spacepy.pycdf import lib
from gdctb_cape_eea.calibration.build_spectra import GDCTB_cape_EEA_Data_Processor
from astropy.time import Time


__all__ = [
    "process_file",
    "parse_l0_sci_packets",
    "parse_hk_packets",
    "l0_sci_data_to_cdf",
    "l0_hk_data_to_cdf",
    "calibrate_file",
    "get_calibration_file",
    "read_calibration_file",
]
APIDS = {
    "HK": [265],
    "SCIENCE": [260],
}

CURRENT_STEPPER_TABLE_FILE = Path("boot_packet.txt")


def _peek_apid(data_filename: Path) -> int:
    """Read the CCSDS APID out of the first packet's primary header (its first 2
    bytes), without needing to know which packet definition (sci vs hk) applies yet.
    """
    with open(data_filename, "rb") as fh:
        header = fh.read(2)
    if len(header) < 2:
        raise ValueError(
            f"{data_filename} is too short to contain a CCSDS primary header."
        )
    first_word = struct.unpack(">H", header)[0]
    return first_word & 0x07FF


def get_stepper_table_for_file(data_filename) -> "StepperTable":
    """Build the StepperTable last selected by a boot/config packet, as recorded in
    CURRENT_STEPPER_TABLE_FILE, rather than looking it up by data_filename.
    """
    stepper_table_name = CURRENT_STEPPER_TABLE_FILE.read_text().strip()
    return StepperTable(stepper_table_name)


def get_apid_for_file(data_filename) -> int:
    """Look up the CCSDS APID that applies to a given registered L0 input file."""
    try:
        return _peek_apid(data_filename)
    except OSError as err:
        raise OSError(f"Could not read input file {data_filename!r}: {err}") from err
    except ValueError as err:
        raise ValueError(
            f"Could not determine APID for input file {data_filename!r}: {err}"
        ) from err


def process_file(data_filename: Path) -> list:
    """
    This is the entry point for the pipeline processing.
    It runs all of the various processing steps required to create a L1A GDCTB_cape CDF File.
    calls:

    .. code-block:: python

        calibrate_file(...)
            parse_science_filename(...)
            parse_l0_sci_packets(...)
            l0_sci_data_to_cdf(...)
                SkymapFactory(...)
                # Use SWXData to populate CDF output file
                GDCTB_cape_EEA_Data_Processor(...).build_GDCTB_capeData()
                # Write the File
                gdctb_cape_eea_data.save(...)
        # A Custom EEA SkymapFactory
        # SWXData


    Parameters
    ----------
    data_filename: `pathlib.Path`
        Fully specificied filename of an input file.
        The file contents: Traditional binary packets in CCSDS format


    Returns
    -------
    output_files: `list[pathlib.Path]`
        Fully specificied filenames for the output CDF files.
        The file contains CDF formatted file with n packets iincluding time and [41,4,32] skymap.

    """
    log.info(f"Processing file {data_filename}.")
    output_files = []

    # Get the Directory of the File
    destination_dir = data_filename.parent

    """
     small_level0_file is parametrized over TEST_PROCESSING in order: a "boot_packet.txt"
       entry persists the stepper table name for the science files that follow, until the
       next boot packet.
    """

    # Determine the APID (and, for science data, the StepperTable) from the file itself.
    if not is_boot_packet(data_filename):
        apid = _peek_apid(data_filename)
        stepper = (
            get_stepper_table_for_file(CURRENT_STEPPER_TABLE_FILE)
            if apid in APIDS["SCIENCE"]
            else None
        )
    else:
        # PUT PACKET IN THE DATABASE:
        store_boot_packet(data_filename)
        # NOTHING ELSE TO DO FOR BOOT PACKETS but to store them for later use
        return output_files

    # Calibrate the Input File
    calibrated_file = calibrate_file(data_filename, destination_dir, stepper, apid)
    output_files.append(calibrated_file)

    # Add Plots to the Output Files if we want
    #  data_plot_files = plot_file(data_filename)
    #  calib_plot_files = plot_file(calibrated_file)

    # add other tasks below
    return output_files


def calibrate_file(
    data_filename: Path, destination_dir, stepper: StepperTable = None, apid: int = None
) -> Path:
    """
    Given an input data file, raise it to the next level
    (e.g. level 0 to level 1, level 1 to quicklook) it and return a new file.

    Parameters
    ----------
    data_filename: `pathlib.Path`
        Fully specificied filename of the input data file.
    destination_dir: `pathlib.Path`
        Fully specificied directory where the output file will be written.

    Returns
    -------
    output_filename: `pathlib.Path`
        Fully specificied filename of the output file.

    """
    log.info(f"Calibrating file:{data_filename}.")
    # stepper = StepperTable(gdctb_cape_eea.stepper_table)

    file_metadata = parse_science_filename(data_filename.name)

    # check if level 0 binary file, if so call appropriate functions
    if (
        file_metadata["instrument"] == gdctb_cape_eea.INST_NAME
        and apid in APIDS["SCIENCE"]
        and file_metadata["level"] == "l0"
    ):
        if stepper is None:
            # Note. To date a boot packet file will not make it here
            raise ValueError(
                f"No StepperTable provided for level-0 science file {data_filename}."
            )

        # call CCSDSPY to parse our packets.
        data = parse_l0_sci_packets(data_filename)
        
        # This is where most of the business logic for converting level 0 science data 
        # to level 1 happens.
        level1_filename = l0_sci_data_to_cdf(
            stepper, data, data_filename, destination_dir
        )
        
        output_filename = level1_filename
    
    elif apid in APIDS["HK"]:
        log.info(f"Processing HK file: {data_filename}.")
        data = parse_hk_packets(data_filename)
        output_filename = l0_hk_data_to_cdf(data, data_filename, destination_dir)
    else:
        raise ValueError(f"The file {data_filename} is not recognized.")

    return output_filename


def parse_l0_sci_packets(data_filename: Path) -> dict:
    """
    Parse a level 0 eea binary file containing CCSDS packets.

    Parameters
    ----------
    data_filename: `pathlib.Path`
        Fully specificied filename

    Returns
    -------
    result: dict
        A dictionary of arrays which includes the ccsds header fields

    Examples
    --------
    >>> import gdctb_cape_eea.calibration as calib
    >>> data_filename = "GDCTB_EEA_l0_2022339-000000_v0.bin"
    >>> data = calib.parse_eea_sci_packets(data_filename)  # doctest: +SKIP
    """
    log.info(f"Parsing packets from file:{data_filename}.")

    pkt = ccsdspy.FixedLength.from_file(
        Path(gdctb_cape_eea._data_directory) / "hermes_EEA_sci_packet_def.csv"
    )
    data = pkt.load(data_filename, include_primary_header=True)

    unique_apids = sorted(set(data["CCSDS_APID"].tolist()))
    log.info(f"Parsed APID(s): {unique_apids}")

    # drop the primary header fields, callers only expect the science fields
    for header_field in (
        "CCSDS_VERSION_NUMBER",
        "CCSDS_PACKET_TYPE",
        "CCSDS_SECONDARY_FLAG",
        "CCSDS_SEQUENCE_FLAG",
        "CCSDS_APID",
        "CCSDS_SEQUENCE_COUNT",
        "CCSDS_PACKET_LENGTH",
    ):
        data.pop(header_field, None)

    return data


def parse_hk_packets(data_filename: Path) -> dict:
    """
    Parse a level 0 eea housekeeping binary file containing CCSDS packets.

    Parameters
    ----------
    data_filename: str
        Fully specificied filename

    Returns
    -------
    result: dict
        A dictionary of arrays which includes the ccsds header fields

    Examples
    --------
    >>> import gdctb_cape_eea.calibration as calib
    >>> data_filename = "GDCTB_EEA_hk_l0_2022339-000000_v0.bin"
    >>> data = calib.parse_hk_packets(data_filename)  # doctest: +SKIP
    """
    log.info(f"Parsing HK packets from file:{data_filename}.")

    pkt = ccsdspy.FixedLength.from_file(
        os.path.join(gdctb_cape_eea._data_directory, "hermes_EEA_hk_packet_def.csv")
    )
    data = pkt.load(data_filename, include_primary_header=True)

    unique_apids = sorted(set(data["CCSDS_APID"].tolist()))
    log.info(f"Parsed APID(s): {unique_apids}")

    # drop the primary header fields, callers only expect the hk fields
    for header_field in (
        "CCSDS_VERSION_NUMBER",
        "CCSDS_PACKET_TYPE",
        "CCSDS_SECONDARY_FLAG",
        "CCSDS_SEQUENCE_FLAG",
        "CCSDS_APID",
        "CCSDS_SEQUENCE_COUNT",
        "CCSDS_PACKET_LENGTH",
    ):
        data.pop(header_field, None)

    return data


def _read_hk_field_catdesc() -> dict:
    """Read the CATDESC text for each HK field from the description column of
    hermes_EEA_hk_packet_def.csv, so field descriptions stay in sync with the
    packet definition instead of being duplicated in code.
    """
    csv_path = os.path.join(gdctb_cape_eea._data_directory, "hermes_EEA_hk_packet_def.csv")
    with open(csv_path, "r") as fp:
        reader = csv.DictReader(fp, skipinitialspace=True)
        return {row["name"].strip(): row["description"].strip() for row in reader}


def _read_hk_fill_field_names() -> set:
    """Names of HK fields declared as data_type "fill" in hermes_EEA_hk_packet_def.csv.

    ccsdspy only bitmasks "uint"/"int" fields, not "fill", so sub-byte fill fields come
    back containing raw, unmasked bits from whatever neighboring field shares that byte.
    Their decoded values are meaningless and shouldn't be written out as measurements.
    """
    csv_path = os.path.join(gdctb_cape_eea._data_directory, "hermes_EEA_hk_packet_def.csv")
    with open(csv_path, "r") as fp:
        reader = csv.DictReader(fp, skipinitialspace=True)
        return {
            row["name"].strip()
            for row in reader
            if row["data_type"].strip().lower() == "fill"
        }


def l0_hk_data_to_cdf(
    data: dict, original_filename: Path, destination_dir: Path
) -> Path:
    """
    Write level 0 eea housekeeping data to a level 1 cdf file.

    Parameters
    ----------
    data: dict
        A dictionary of arrays which includes the housekeeping fields
        (as returned by parse_hk_packets), including SHCOARSE/SHFINE.
    original_filename: Path
        The Path to the originating file.
    destination_dir: Path
        The directory to write the output cdf file to.

    Returns
    -------
    output_filename: Path
        Fully specificied filename of cdf file
    """
    file_metadata = parse_science_filename(original_filename.name)

    epoch = ccsds_to_cdf_time.help_convert_eaa(data)
    iso_datetimes = Time([lib.tt2000_to_datetime(e) for e in epoch])
    hk_timeseries = TimeSeries(time=iso_datetimes)

    bare_attrs = SWXData.global_attribute_template(gdctb_cape_eea.INST_NAME, "l1", "1.0.0")
    # Distinguishes this from the sci L1 CDF in the output filename (Logical_file_id).
    bare_attrs["Instrument_mode"] = "hk"
    gdctb_cape_eea_hk_data = SWXData(timeseries=hk_timeseries, meta=bare_attrs)

    hk_catdesc = _read_hk_field_catdesc()
    hk_fill_fields = _read_hk_fill_field_names()

    # SHCOARSE/SHFINE were only needed to derive the epoch above. FILL fields are skipped
    # since ccsdspy returns their raw, unmasked bits (see _read_hk_fill_field_names).
    # Everything else is stored as raw, dimensionless counts for now since calibration
    # curves for voltages/temperatures are not yet defined (same approach as the science data).
    # I did go to the trouble to convert thier raw values to real voltages and currents to
    # verify that I was parsing everything correctly but was asked to back that code out (I still have that branch)
    # THIS IS THE DATA WE WANT IN THE DATABASE (barring the units conversion above)
    for field, values in data.items():
        if field in ("SHCOARSE", "SHFINE") or field in hk_fill_fields:
            continue
        try:
            gdctb_cape_eea_hk_data.add_measurement(
                f"gdctb_cape_eea_{field.lower()}",
                astropy_units.Quantity(values, astropy_units.dimensionless_unscaled),
                meta={"CATDESC": hk_catdesc.get(field, f"HK field {field}")},
            )
        except Exception as e:
            raise ValueError(f"Could not add HK field {field}") from e

    try:
        cdf_path = gdctb_cape_eea_hk_data.save(destination_dir, True)
    except Exception as e:
        log.error(e)
        sys.exit(2)

    return cdf_path


def l0_sci_data_to_cdf(
    stepper, data: dict, original_filename: Path, destination_dir: Path
) -> Path:
    """
    Write level 0 eea science data to a level 1 cdf file.

    Parameters
    ----------
    data: dict
        A dictionary of arrays which includes the ccsds header fields
    original_filename: `pathlib.Path`
        The Path to the originating file.
    destination_dir: `pathlib.Path`
        The directory where the output file will be written.

    Returns
    -------
    output_filename: `pathlib.Path`
        Fully specificied filename of cdf file

    Examples
    --------
    >>> from pathlib import Path
    >>> from swxsoc.util.util import parse_science_filename
    >>> import gdctb_cape_eea.calibration as calib
    >>> data_filename = Path("GDCTB_EEA_l0_2022339-000000_v0.bin")
    >>> metadata = parse_science_filename(data_filename)  # doctest: +SKIP
    >>> data_packets = calib.parse_l0_sci_packets(data_filename)  # doctest: +SKIP
    >>> cdf_filename = calib.l0_sci_data_to_cdf(data_packets, data_filename)  # doctest: +SKIP
    """

    # this is transferring name.bin to name.cdf
    file_metadata = parse_science_filename(original_filename.name)

    cdf_filename = original_filename.parent / create_science_filename(
        file_metadata["instrument"],
        file_metadata["time"],
        "l1",
        f'1.0.{file_metadata["version"]}',
    )
    if data:
        """
        gdctb_cape_eea.stepper_table for now is defined in gdctb_cape_eea/gdctb_cape_eea/__init__.py
        """

        # calibration_file = get_calibration_file(gdctb_cape_eea.stepper_table)
        # read_calibration_file(calibration_file)

        myEEA = EEA(file_metadata)
        # SkymapFactory, now as does FPI, also populates my EEA data model
        skymap_factory(data, stepper, myEEA)

        # In the beginning, testing phase of this project, while we adjust things.
        # This will show us which packets have a workable amount of data
        # most_active = np.where(np.array(myEEA.stats) > 150)
        # these eample start times are also something I would like to keep around for a while
        # example_start_times = Time(
        #    [lib.tt2000_to_datetime(e) for e in myEEA.Epoch[0:10]]
        # )

        n_sweeps = len(myEEA.Epoch)

        # https://swxsoc.readthedocs.io/en/latest/user-guide/reading_writing_data.html
        # https://swxsoc.readthedocs.io/en/latest/generated/api/swxsoc.swxdata.SWXData.html#swxsoc.swxdata.SWXData
        gdctb_cape_eea_factory = GDCTB_cape_EEA_Data_Processor(myEEA)
        gdctb_cape_eea_factory.build_GDCTB_capeData()

        try:
            # this writes out the data to CDF file format
            cdf_path = gdctb_cape_eea_factory.gdctb_cape_eea_data.save(
                output_path=destination_dir, overwrite=True
            )
        except Exception as e:
            log.error(e)
            sys.exit(2)

    return cdf_path


def get_calibration_file(data_filename: Path, time=None) -> Path:
    """
    Given a time, return the appropriate calibration file.
    Parameters
    ----------
    data_filename: `pathlib.Path`
        Fully specificied filename of the non-calibrated file (data level < 2)
    time: ~astropy.time.Time

    Returns
    -------
    calib_filename: `pathlib.Path`
        Fully specificied filename for the appropriate calibration file.

    Examples
    --------
    """
    return Path(gdctb_cape_eea._calibration_directory) / data_filename


def read_calibration_file(calib_filename: Path):
    """
    Given a calibration, return the calibration structure.

    Parameters
    ----------
    DJG says that energies and angles may change
    calib_filename: `pathlib.Path`
        Fully specificied filename of the non-calibrated file (data level < 2)
        0 1
    Returns
    -------
    output_filename: `pathlib.Path`
        Fully specificied filename of the appropriate calibration file.

    Examples
    --------
    """
    lines = read_file(calib_filename)
    calib.energies = []
    calib.deflections = []
    for line in lines:
        calib.energies.append(int(line[8:10], 16))
        calib.deflections.append(int(line[10:12], 16))


def is_binary_file(file_path, block_size=1024):
    """Returns True if the file contains binary data, False if it is clean ASCII."""
    try:
        with open(file_path, "rb") as f:
            block = f.read(block_size)

            # A null byte is a definitive indicator of a binary format
            if b"\x00" in block:
                return True

            # If any byte is outside the valid ASCII range (0-127), it's binary
            if any(byte > 127 for byte in block):
                return True

            return False
    except IOError:
        print(f"Error: Could not read file {file_path}")
        return False


def is_ascii_file(file_path, block_size=1024):
    """Returns True if the file contains only valid 7-bit ASCII characters."""
    try:
        with open(file_path, "rb") as f:
            block = f.read(block_size)

            # A null byte means it is a binary file, not ASCII text
            if b"\x00" in block:
                return False

            # ASCII characters only use byte values from 0 to 127
            if any(byte > 127 for byte in block):
                return False

            return True
    except IOError:
        print(f"Error: Could not read file {file_path}")
        return False


def is_boot_packet(file_path):
    """Returns True if the file is a boot packet (ASCII text), False otherwise."""
    return is_ascii_file(file_path)


def store_boot_packet(file_path):
    """Stores the boot packet info in DATABASE for later use.
    currently stubbed to write the name of the current stepper to
    a file called boot_packet.txt"""

    CURRENT_STEPPER_TABLE_FILE.write_text(file_path.name)
