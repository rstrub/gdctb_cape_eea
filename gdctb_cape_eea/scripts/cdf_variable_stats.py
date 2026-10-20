"""
Standalone diagnostic script: print non-zero statistics for every numeric
variable in a CDF file.

For each variable, reports:
    n_records          - total number of records (length of the first axis)
    n_nonzero_records   - number of records containing at least one non-zero, non-fill value
    n_nonzero_values    - number of individual non-zero, non-fill elements across the variable
    avg/max/min_nonzero - average, max, and min over only the non-zero, non-fill elements

Elements equal to the variable's FILLVAL attribute (the standard ISTP/CDF fill-value
marker, e.g. -1e+31 for reals) are excluded from all of the above, since they are
padding, not real data.

Usage
-----
    python -m hermes_eea.scripts.cdf_variable_stats path/to/file.cdf
    python -m hermes_eea.scripts.cdf_variable_stats path/to/file.cdf --variable hermes_eea_accum
    python -m hermes_eea.scripts.cdf_variable_stats path/to/file.cdf --csv out.csv
"""

import argparse
import csv
import shutil
import textwrap

import numpy as np
from spacepy import pycdf


def compute_variable_stats(cdf_path: str, variables: list | None = None ) -> dict:
    """
    Compute non-zero, non-fill statistics for each requested (or all numeric) variable in a CDF file.

    Returns
    -------
    dict mapping variable name -> dict of n_records, n_nonzero_records, n_nonzero_values,
    avg_nonzero, max_nonzero, min_nonzero (the latter three are None if there are no
    non-zero, non-fill values at all).
    """
    stats = {}
    with pycdf.CDF(cdf_path) as cdf:
        var_names = variables if variables else list(cdf.keys())
        for name in var_names:
            var = cdf[name]
            data = np.asarray(var[:])
            if not np.issubdtype(data.dtype, np.number) or data.ndim == 0:
                continue  # skip non-numeric (e.g. Epoch/time, string) and scalar variables

            fillval = var.attrs.get("FILLVAL")
            valid_mask = np.ones(data.shape, dtype=bool) if fillval is None else data != fillval

            n_records = data.shape[0]
            per_record_valid_nonzero = (data != 0) & valid_mask
            n_nonzero_records = int(np.any(per_record_valid_nonzero.reshape(n_records, -1), axis=1).sum())

            nonzero_values = data[per_record_valid_nonzero]
            n_nonzero_values = int(nonzero_values.size)
            if n_nonzero_values:
                avg_nonzero = float(nonzero_values.mean())
                max_nonzero = float(nonzero_values.max())
                min_nonzero = float(nonzero_values.min())
            else:
                avg_nonzero = max_nonzero = min_nonzero = None

            stats[name] = {
                "catdesc": var.attrs.get("CATDESC", name),
                "units": var.attrs.get("UNITS", ""),
                "n_records": n_records,
                "n_nonzero_records": n_nonzero_records,
                "n_nonzero_values": n_nonzero_values,
                "avg_nonzero": avg_nonzero,
                "max_nonzero": max_nonzero,
                "min_nonzero": min_nonzero,
            }
    return stats


def print_stats(stats: dict) -> None:
    name_width, n_records_width, nz_records_width, nz_values_width, stat_width = 25, 10, 11, 10, 12
    n_gaps = 7  # spaces between the 8 columns
    fixed_width = name_width + n_records_width + nz_records_width + nz_values_width + 3 * stat_width + n_gaps
    # size CATDESC to whatever's left of the actual terminal width, so the row never
    # overflows and gets corrupted by the terminal's own soft-wrap on copy/paste
    terminal_width = shutil.get_terminal_size(fallback=(120, 24)).columns
    label_width = max(20, terminal_width - fixed_width)

    header = (
        f"{'variable':{name_width}s} {'CATDESC':{label_width}s} {'n_records':>{n_records_width}s} "
        f"{'nz_records':>{nz_records_width}s} {'nz_values':>{nz_values_width}s} "
        f"{'avg_nz':>{stat_width}s} {'max_nz':>{stat_width}s} {'min_nz':>{stat_width}s}"
    )
    print(header)
    print("-" * len(header))
    for name, s in stats.items():
        avg = f"{s['avg_nonzero']:.4g}" if s["avg_nonzero"] is not None else "-"
        vmax = f"{s['max_nonzero']:.4g}" if s["max_nonzero"] is not None else "-"
        vmin = f"{s['min_nonzero']:.4g}" if s["min_nonzero"] is not None else "-"
        label = f"{s['catdesc']} ({s['units']})" if s["units"] else s["catdesc"]
        short_name = name.removeprefix("hermes_eea_")
        label_lines = textwrap.wrap(label, label_width) or [""]
        print(
            f"{short_name:{name_width}s} {label_lines[0]:{label_width}s} {s['n_records']:{n_records_width}d} "
            f"{s['n_nonzero_records']:{nz_records_width}d} {s['n_nonzero_values']:{nz_values_width}d} "
            f"{avg:>{stat_width}s} {vmax:>{stat_width}s} {vmin:>{stat_width}s}"
        )
        for extra_line in label_lines[1:]:
            print(f"{'':{name_width}s} {extra_line:{label_width}s}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cdf_path", help="Path to the CDF file")
    parser.add_argument(
        "--variable", action="append", help="CDF variable name to include (repeatable); default is all variables"
    )
    parser.add_argument("--csv", help="Optional path to also write the stats as CSV")
    args = parser.parse_args()

    results = compute_variable_stats(args.cdf_path, args.variable)
    print_stats(results)

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["variable", "catdesc", "units", "n_records", "n_nonzero_records", "n_nonzero_values",
                            "avg_nonzero", "max_nonzero", "min_nonzero"],
            )
            writer.writeheader()
            for name, s in results.items():
                writer.writerow({"variable": name, **s})
