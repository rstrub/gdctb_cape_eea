# see license/LICENSE.rst
import os
from pathlib import Path

try:
    from ._version import version as __version__
    from ._version import version_tuple
except ImportError:
    __version__ = "unknown version"
    version_tuple = (0, 0, "unknown version")

import swxsoc
from swxsoc import print_config

# Force the mission environment variable and reconfigure regardless of import order
os.environ["SWXSOC_MISSION"] = "gdctb"
swxsoc.reconfigure()

# Load user configuration
config = swxsoc.config

log = swxsoc.log

# Then you can be explicit to control what ends up in the namespace,
__all__ = ["config", "print_config"]

_package_directory = Path(__file__).parent
_data_directory = _package_directory / "data"
_test_files_directory = _package_directory / "data" / "test"
_calibration_directory = _data_directory / "calibration"

log.debug(f"gdctb_cape_eea version: {__version__}")

INSTRUMENT_NAME = "cape-eea"  # A valid SWXSOC instrument name.  It's defined in the gdctb mission section of swxsoc's data/config.yml

INST_NAME = INSTRUMENT_NAME
# Must use a hyphen, not an underscore: swxsoc's create_science_filename()/parse_science_filename()
# split filenames on "_" and locate fields by position, so an underscore here (e.g. "cape_eea")
# would be split into extra tokens and break parsing. "cape-eea" survives the split intact,
# producing filenames like gdctb_cape-eea_l1_20000101T170901_v1.0.0.cdf.


def getCalibrationDirectory():
    return _calibration_directory
