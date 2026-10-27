import os
from pathlib import Path

import ccsdspy

import gdctb_cape_eea
from gdctb_cape_eea.io import read_file

# Stub "database": boot packet BTABSEL value -> stepper table file name
# THIS IS OUR DATABASE.
CURRENT_STEPPER_TABLE_FILE = Path("boot_packet.txt")
# THE BOOT PACKET CAN ONLY REFER TO A PARTICULAR STEPPER TABLE by BTABSEL[0], BTABSEL[1], etc.
STEPPER_TABLE_FOR_BTABSEL = {
    0: "ptb_esastepped_undeflected_stepper.txt",
    1: "flight_stepper.txt",
    2: "ptb_esastepped_deflected_stepper.txt",
}


class StepperTable:
    def __init__(self, stepper_table: Path):
        if not stepper_table:
            raise ValueError(
                f"stepper_table must be a non-empty filename, got {stepper_table!r}"
            )
        self.stepper_table_file = os.path.join(
            gdctb_cape_eea._calibration_directory, stepper_table
        )
        self.parse_stepper_table()
        issues = validate_stepper_table(self)
        if issues:
            raise ValueError(
                f"Stepper table {stepper_table!r} failed validation:\n"
                + "\n".join(f"- {issue}" for issue in issues)
            )
        self.n_defl = len(get_unique_list(self.deflections))
        self.n_energies = len(get_unique_list(self.energies))

        self.v_defl = [-16.875, -5.625, 5.625, 16.875]

        self.v_energies = [
            2.18000000e00,
            2.63177330e00,
            3.17717004e00,
            3.83559233e00,
            4.63046306e00,
            5.59005918e00,
            6.74851766e00,
            8.14704980e00,
            9.83540739e00,
            1.18736525e01,
            1.43342944e01,
            1.73048684e01,
            2.08910507e01,
            2.52204172e01,
            3.04469818e01,
            3.67566761e01,
            4.43739626e01,
            5.35698211e01,
            6.46713874e01,
            7.80735920e01,
            9.42532085e01,
            1.13785815e02,
            1.37366271e02,
            1.65833433e02,
            2.00200000e02,
            2.39800000e02,
            3.17794829e02,
            4.21157437e02,
            5.58138682e02,
            7.39673007e02,
            9.80251281e02,
            1.29907752e03,
            1.72160182e03,
            2.28155195e03,
            3.02362557e03,
            4.00705827e03,
            5.31035195e03,
            7.03754125e03,
            9.32649800e03,
            1.23599368e04,
            1.63800000e04,
        ]

    def parse_stepper_table(self):
        """
        Parse the stepper table file and populate the energies and deflections lists.
        """
        lines = read_file(os.path.join(self.stepper_table_file))
        self.energies = []
        self.deflections = []
        for line in lines:
            if "#" not in line:
                try:
                    [energy, deflection] = line.split(",")
                    self.energies.append(float(energy))
                    self.deflections.append(float(deflection))
                except ValueError:
                    continue

    def parse_old_stepper_table(self):
        """
        Given a calibration, return the calibration structure.

        Parameters
        ----------
        DJG says that energies and angles may change
        calib_filename: str
            Fully specificied filename of the non-calibrated file (data level < 2)
            0 1
        Returns
        -------
        output_filename: str
            Fully specificied filename of the appropriate calibration file.

        Examples
        --------
        """

        lines = read_file(os.path.join(self.stepper_table_file))
        self.energies = []
        self.deflections = []
        for line in lines:
            self.energies.append(int(line[8:10], 16))
            self.deflections.append(int(line[10:12], 16))


def get_unique_list(arr):

    unique_list = []

    for x in arr:
        if x not in unique_list:
            unique_list.append(x)
    return unique_list


# Hard FOV centroid deflection requirement is +/-17 deg; the as-designed/as-built
# optics and stepper tables operate over a narrower +/-16.875 deg range. Used here
# as a sanity bound on the deflection column, not a strict engineering spec check.
MAX_DEFLECTION_DEG = 90.0


def validate_stepper_table(stepper: "StepperTable") -> list:
    """
    Sanity-check a parsed StepperTable's energy/deflection columns.

    I'm just checking that the stepper table is in roughly the expected format:
    1. energies are > 0 and there are very few if any repeats
    2. declinations angles are < 90 and the repeat a lot. At least a lot more than energies.



    Parameters
    ----------
    stepper: StepperTable
        An already-parsed StepperTable instance.

    Returns
    -------
    issues: list[str]
        Human readable descriptions of any problems found. An empty list
        means the table passed every check.
    """
    issues = []

    energies = stepper.energies
    deflections = stepper.deflections

    if not energies or not deflections:
        issues.append("Stepper table has no parsed energy/deflection rows.")
        return issues

    if len(energies) != len(deflections):
        issues.append(
            f"energies ({len(energies)}) and deflections ({len(deflections)}) "
            "have different lengths; the file may be malformed."
        )

    # Range checks
    bad_deflections = [d for d in deflections if abs(d) > MAX_DEFLECTION_DEG]
    if bad_deflections:
        issues.append(
            f"{len(bad_deflections)} deflection value(s) exceed "
            f"+/-{MAX_DEFLECTION_DEG} deg (e.g. {bad_deflections[:5]}); "
            "the energy/deflection columns may be swapped."
        )

    non_positive_energies = [e for e in energies if e <= 0]
    if non_positive_energies:
        issues.append(
            f"{len(non_positive_energies)} energy value(s) are <= 0 eV "
            f"(e.g. {non_positive_energies[:5]}); energies must be positive."
        )

    # Repetition check: deflection should repeat a lot more than energy does.
    n_unique_energies = len(get_unique_list(energies))
    n_unique_deflections = len(get_unique_list(deflections))
    energy_unique_ratio = n_unique_energies / len(energies)
    deflection_unique_ratio = n_unique_deflections / len(deflections)

    if deflection_unique_ratio >= energy_unique_ratio:
        issues.append(
            "Deflection column does not repeat more than the energy column "
            f"(unique deflections: {n_unique_deflections}/{len(deflections)} "
            f"= {deflection_unique_ratio:.2f}, unique energies: "
            f"{n_unique_energies}/{len(energies)} = {energy_unique_ratio:.2f}); "
            "the energy/deflection columns may be swapped."
        )

    return issues


def get_stepper_table_for_file(data_filename) -> "StepperTable":
    """Build the StepperTable last selected by a boot/config packet, as recorded in
    CURRENT_STEPPER_TABLE_FILE, rather than looking it up by data_filename.
    """
    stepper_table_name = CURRENT_STEPPER_TABLE_FILE.read_text().strip()
    return StepperTable(stepper_table_name)


def get_stepper_table_name_for_btabsel(btabsel: int) -> str:
    """Look up the stepper table file name selected by a boot packet BTABSEL value."""
    try:
        return STEPPER_TABLE_FOR_BTABSEL[int(btabsel)]
    except KeyError:
        raise ValueError(
            f"No stepper table is defined for BTABSEL={btabsel}; "
            f"expected one of {sorted(STEPPER_TABLE_FOR_BTABSEL)}."
        ) from None


def read_btabsel(file_path) -> int:
    """Read BTABSEL from the last packet of a binary boot packet file."""
    pkt = ccsdspy.FixedLength.from_file(
        os.path.join(
            gdctb_cape_eea._data_directory, "gdctb_cape-eea_boot_packet_def.csv"
        )
    )
    result = pkt.load(file_path)
    return int(result["BTABSEL"][-1])


def is_ascii_file(file_path, block_size=1024):
    """Returns True if the file contains only valid 7-bit ASCII characters."""
    try:
        with open(file_path, "rb") as f:
            block = f.read(block_size)

            # A null byte means it is a binary file, not ASCII text
            if b"\x00" in block:
                return False

            # ASCII characters only use byte values from 0 to 127
            return not any(byte > 127 for byte in block)
    except OSError:
        print(f"Error: Could not read file {file_path}")
        return False


def store_boot_packet(file_path):
    """Stores the boot packet info in DATABASE for later use.
    Currently stubbed to write the name of the stepper table selected by the
    boot packet's BTABSEL to a file called boot_packet.txt.
    ASCII boot files already contain the stepper table name as their file name."""

    file_path = Path(file_path)
    if is_ascii_file(file_path):
        stepper_table_name = file_path.name
    else:
        stepper_table_name = get_stepper_table_name_for_btabsel(read_btabsel(file_path))
    CURRENT_STEPPER_TABLE_FILE.write_text(stepper_table_name)
