import gdctb_cape_eea
from pathlib import Path
from gdctb_cape_eea.io.file_tools import read_file
from gdctb_cape_eea.Stepper.StepperTable import StepperTable, validate_stepper_table
from pathlib import Path
import pytest


def test_read_file():
    assert read_file("./gdctb_cape_eea/data/calibration/flight_stepper.txt") is not None


@pytest.fixture(scope="session")  # this is a pytest fixture
def first_stepper_file(tmp_path_factory):
    fn = Path("flight_stepper.txt")
    return fn


def test_characterize_stepper(first_stepper_file):
    stepper = StepperTable(first_stepper_file)
    assert len(stepper.energies) == 164


@pytest.mark.parametrize(
    "stepper_table_file",
    ["flight_stepper.txt", "ptb_esastepped_undeflected_stepper.txt"],
)
def test_validate_stepper_table_passes(stepper_table_file):
    stepper = StepperTable(stepper_table_file)
    assert validate_stepper_table(stepper) == []


def test_validate_stepper_table_catches_swapped_columns():
    stepper = StepperTable("flight_stepper.txt")
    # Deliberately swap the parsed columns to simulate a mis-parsed/malformed file.
    stepper.energies, stepper.deflections = stepper.deflections, stepper.energies
    issues = validate_stepper_table(stepper)
    assert issues != []
    assert any("may be swapped" in issue for issue in issues)


def test_validate_stepper_table_catches_empty_table():
    stepper = StepperTable("flight_stepper.txt")
    stepper.energies = []
    stepper.deflections = []
    issues = validate_stepper_table(stepper)
    assert issues == ["Stepper table has no parsed energy/deflection rows."]


def test_stepper_table_raises_on_swapped_columns_file(tmp_path, monkeypatch):
    # Write a stepper table file with the energy/deflection columns swapped:
    # a small, repeated set of deflection-sized values in the energy column,
    # and large, mostly-unique, energy-sized values in the deflection column.
    # Confirm StepperTable() rejects it automatically at construction time,
    # rather than silently loading it.
    defl_like_values = [-16.875, -5.625, 5.625, 16.875]
    bad_table = tmp_path / "swapped_stepper.txt"
    bad_table.write_text(
        "\n".join(
            f"{defl_like_values[i % len(defl_like_values)]}, {100.0 + i}"
            for i in range(50)
        )
    )
    monkeypatch.setattr(gdctb_cape_eea, "_calibration_directory", tmp_path)

    with pytest.raises(ValueError, match="failed validation"):
        StepperTable("swapped_stepper.txt")
