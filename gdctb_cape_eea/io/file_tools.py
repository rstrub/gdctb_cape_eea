from pathlib import Path

from ccsdspy import FixedLength

"""
This module provides a generic file reader.
"""

__all__ = ["read_ccsds", "read_file"]


def read_file(data_filename: Path):
    """
    Read a file.

    Parameters
    ----------
    data_filename: `pathlib.Path`
        A file to read.

    Returns
    -------
    data: str

    Examples
    --------
    """
    try:
        with open(data_filename) as fh:
            return fh.readlines()
    except (FileNotFoundError, PermissionError) as err:
        raise FileNotFoundError(f"Could not read: {data_filename}") from err


def read_ccsds(filename: Path, pkt_def: FixedLength):
    """
    Read a ccsds packet file.

    Parameters
    ----------
    filename: `pathlib.Path`
        A file to read.

    pkt_def: `ccsdspy.FixedLength`
        CCSDS packet definition

    Returns
    -------
    `OrderedDict` mapping field names to NumPy arrays.
    """
    result = pkt_def.load(filename)
    return result
