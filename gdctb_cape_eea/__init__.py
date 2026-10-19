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
_reconfigure = getattr(swxsoc, "reconfigure", None) or swxsoc._reconfigure
_reconfigure()

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

INSTRUMENT_NAME = "cape_eea"

# Kept as a separate alias (rather than inlining INSTRUMENT_NAME everywhere) to mirror
# the ported gdctb_cape_eea code's INST_NAME/INST_SHORTNAME/INST_TARGETNAME naming, and to
# match swxsoc's {mission}_{instrument} package-naming convention (get_instrument_package()):
# the registered instrument "name" must equal this package's own name suffix ("cape_eea")
# so that, once available, get_instrument_package("cape_eea") resolves to "gdctb_cape_eea".
INST_NAME = INSTRUMENT_NAME
# Must use a hyphen, not an underscore: swxsoc's create_science_filename()/parse_science_filename()
# split filenames on "_" and locate fields by position, so an underscore here (e.g. "cape_eea")
# would be split into extra tokens and break parsing. "cape-eea" survives the split intact,
# producing filenames like gdctb_cape-eea_l1_20000101T170901_v1.0.0.cdf.
INST_SHORTNAME = "cape-eea"
# Matches INST_SHORTNAME so L0 .bin filenames (gdctb_cape-eea_l0_..._v0.bin, validated against
# inst_targetnames) and L1+ .cdf filenames (gdctb_cape-eea_l1_..._v1.0.0.cdf, validated against
# inst_shortnames) use the same instrument token.
INST_TARGETNAME = "cape-eea"
INST_FULLNAME = "Electron Electrostatic Analyzer"
INST_TO_SHORTNAME = {INST_NAME: INST_SHORTNAME}
INST_TO_TARGETNAME = {INST_NAME: INST_TARGETNAME}

# The installed swxsoc package does not (yet) ship a "gdctb" entry in its default
# missions_data config, so config["mission"]["inst_*"] come back empty and
# swxsoc.util.util.parse_science_filename()/create_science_filename() would reject
# every gdctb_cape-eea_* filename. Register this instrument directly so filename
# validation works regardless of which swxsoc config.yml happened to be loaded.
if not config["mission"]["inst_names"]:
    config["mission"].update(
        {
            "file_extension": ".cdf",
            "inst_names": [INST_NAME],
            "inst_shortnames": [INST_SHORTNAME],
            "inst_fullnames": [INST_FULLNAME],
            "inst_targetnames": [INST_TARGETNAME],
            "inst_to_shortname": dict(INST_TO_SHORTNAME),
            "inst_to_fullname": {INST_NAME: INST_FULLNAME},
            "inst_to_targetname": dict(INST_TO_TARGETNAME),
        }
    )


def getCalibrationDirectory():
    return _calibration_directory
