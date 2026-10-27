.. _calibration_plan:

**********************************
cape_eea Calibration Plan
**********************************

Overall Calibration Scheme
==========================
This section summarizes the calibration philosophy and identifies any heritage tied to the
calibration schemes of related missions and instruments.

Science Data needs to reference a Stepper Table that is referenced in the boot packet.
Versions so far read all of the packets from a sweep defined by the Stepper Table and place the entire
sweep into a single CDF Packet
House Keeping HK data has no boot packet dependencies.

Boot Packet and Stepper Table Selection
---------------------------------------
Boot packets (APID 266) are read using the packet definition ``gdctb_cape-eea_boot_packet_def.csv``.
The 3-bit ``BTABSEL`` field selects the stepper table that applies to the science data that follows,
until the next boot packet. The assignment for each binary boot packet(file) ``BTABSEL`` value is:

+---------+--------------------------------------------+
| BTABSEL | Stepper table                              |
+=========+============================================+
| 0       | ``ptb_esastepped_undeflected_stepper.txt`` |
+---------+--------------------------------------------+
| 1       | ``flight_stepper.txt``                     |
+---------+--------------------------------------------+
| 2       | ``ptb_esastepped_deflected_stepper.txt``   |
+---------+--------------------------------------------+

Any other ``BTABSEL`` value raises a ``ValueError``.

Processing a boot packet does nothing else except record the selected table name in
``boot_packet.txt``, a stub standing in for a database. Science processing reads
``boot_packet.txt`` to build the ``StepperTable`` it uses. The code lives in
:py:mod:`gdctb_cape_eea.Stepper.StepperTable` (``read_btabsel``, ``get_stepper_table_name_for_btabsel``,
``store_boot_packet`` and ``get_stepper_table_for_file``). ASCII boot files are not parsed; their file
name is taken as the stepper table name.

Pre-flight Calibration Plans
============================
This section details how unit level (e.g., individual detectors) and system level (e.g., instrument
subsystem) are tested and calibrated to verify that they will meet the expected performance
parameters prior to placement (i.e., launch) into the relevant operational environment.

<Subsystem name> Pre-flight Calibrations
----------------------------------------
This subsection describes the specific testing and examination methods used to
characterize the build and performance of each subsystem or component (e.g., diffraction
gratings, CCDs)

Instrument Description
======================
This subsection describes the primary scientific objectives of the instrument, its hardware,
physical configuration, etc. This subsection lists the major elements of the instrument and
provides a schematic of the conceptual design. Known issues due to external factors that
could impact any long-term comparison or analysis (e.g., optical distortion due to gradual
radiation degradation) should be captured.

In-flight Tracking of Short-Term Changes
========================================
This section identifies any potential factors in the operational environment (e.g., radiation,
temperature fluctuations, exposure-related degradation) that could eventually result in off-
nominal changes in the instrument’s measurements. The methods used to identify and track
these changes are also described.

Long-term Absolute Calibration Tracking (Re-Calibration)
========================================================
This section identifies any periodic re-calibration to absolute standards to be used over the
course of the mission.

Validation
==========
This describes the use of any other measurements (via complementary instruments) or models
to validate the instrument’s measurements
