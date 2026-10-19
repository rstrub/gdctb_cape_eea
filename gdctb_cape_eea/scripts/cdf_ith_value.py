"""
Standalone diagnostic script: print the i-th element of a given CDF variable
for every record (row) in the file.

Usage
-----
    python -m hermes_eea.scripts.cdf_ith_value path/to/file.cdf --variable hermes_eea_counter2 --index 34
"""

import argparse

import numpy as np
from spacepy import pycdf


def ith_value_per_record(cdf_path: str, variable: str, index: int) -> list:
    with pycdf.CDF(cdf_path) as cdf:
        data = np.array(cdf[variable][:])
    if data.ndim < 2:
        raise ValueError(f"{variable!r} has shape {data.shape}; expected at least 2 dims (records, ...)")
    return data[:, index].tolist()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdf_path", help="Path to the CDF file")
    parser.add_argument("--variable", required=True, help="CDF variable name to read")
    parser.add_argument("--index", type=int, required=True, help="Index into each record's array")
    args = parser.parse_args()

    values = ith_value_per_record(args.cdf_path, args.variable, args.index)
    print(f"{args.variable}[:, {args.index}] ({len(values)} records):")
    print(values)
