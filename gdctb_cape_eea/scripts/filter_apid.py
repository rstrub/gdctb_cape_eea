"""
Utility: extract only the packets for one APID out of a mixed CCSDS binary
file and write them to a new file.
"""

from ccsdspy.utils import split_by_apid


def filter_apid(input_filename: str, output_filename: str, apid: int) -> int:
    """Write only the packets matching `apid` from `input_filename` to `output_filename`.

    Returns
    -------
    n_bytes: int
        Number of bytes written to the output file.
    """
    streams_by_apid = split_by_apid(input_filename)
    if apid not in streams_by_apid:
        raise ValueError(
            f"APID {apid} not found in {input_filename}. "
            f"Available APIDs: {sorted(streams_by_apid)}"
        )

    data = streams_by_apid[apid].read()
    with open(output_filename, "wb") as fh:
        fh.write(data)

    return len(data)
