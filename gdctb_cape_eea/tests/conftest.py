import pytest

from gdctb_cape_eea.Stepper.StepperTable import CURRENT_STEPPER_TABLE_FILE

TEST_PROCESSING = [
    "20261014040843395730000__has_only_boot_packet.bin",
    "gdctb_cape-eea_l0_20261015-234049_v0.bin",

    "20261014040843395730000__has_only_boot_packet_btabsel_2.bin",
    "gdctb_cape-eea_l0_2026161-132236_v0.bin",

    "20261014040843395730000__has_only_boot_packet.bin",

    "gdctb_cape-eea_hk_l0_2026161-132237_v0.bin",
    "gdctb_cape-eea_hk_l0_2026023-000000_v0.bin",
]


# STEPPER_TABLE_FOR_FILE, get_stepper_table_for_file, and get_apid_for_file now live in
# gdctb_cape_eea.calibration.calibration (the production module) and are re-exported here so
# process_file() and the tests share a single registry instead of drifting out of sync.


@pytest.fixture(autouse=True, scope="session")
def seed_boot_packet():
    """Seed CURRENT_STEPPER_TABLE_FILE ("boot_packet.txt") with a known-good default stepper
    table name before any test runs.

    Production code only ever creates this file as a side effect of processing a boot-packet
    TEST_PROCESSING entry (see calib.store_boot_packet), via a bare relative path resolved
    against whatever directory the process happens to run from. That means tests that need a
    stepper table (e.g. verify_l1a's get_stepper_table_for_file call) would fail with a
    FileNotFoundError unless an earlier test in the same run order happened to populate it
    first. Writing a default here makes the file available regardless of test order,
    filtering, or isolation. Tests that do process a real boot-packet entry still overwrite it
    with the real value, same as production.
    """
    CURRENT_STEPPER_TABLE_FILE.write_text("flight_stepper.txt")
