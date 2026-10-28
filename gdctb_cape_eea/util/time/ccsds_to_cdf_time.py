"""Utils for the CCSDSPy package."""

__author__ = "Richard Strub <richard.f.strub@nasa.gov>"

import numpy as np

# FPI used 1325419167816000000; EEA uses this offset.
TAI_EPOCH_TT2000_NS = -64184000000
NANOS_PER_MICRO = 1000
NANOS_PER_SEC = 1000000000




def convert_ccsds_times_to_cdf(decoded) -> np.ndarray:
    """
    Parameters
    ----------
    coarse - CCSDSPY time parm
    fine     CCSDSPY time parm
    CCSDS telemetry files often include this COARSE and FINE times
    that we translate into CDF EPOCH according to examples in original
    IDL FPI Ground System code.

    Returns
    -------
    CDF-EPOCH time. Nanoseconds since the TT2000 epoch.
    tai_time["taiEpoch_tt2000"] for FPI was different than for EEA.
    I am not sure if this was chosen arbitrarily or through direction from Hermes SOC
    """
    coarse = np.uint(decoded["SHCOARSE"])
    fine = np.uint(decoded["SHFINE"])
    p1 = np.int64(coarse) * NANOS_PER_SEC
    p2 = np.int64(fine) * NANOS_PER_MICRO
    epoch = p1 + p2
    result = np.uint64(epoch - TAI_EPOCH_TT2000_NS)
    return result
