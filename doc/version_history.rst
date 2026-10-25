.. py:currentmodule:: lsst.ts.dream.csc

.. _lsst.ts.dream.csc.version_history:

###############
Version History
###############

.. towncrier release notes start

v0.5.13 (2026-04-15)
====================

Bug Fixes
---------

- Avoided fault in case of missing weather telemetry by reporting bad weather to DREAM instead. (`OSW-1824 <https://rubinobs.atlassian.net//browse/OSW-1824>`_)
- Avoided canceling the health monitor within itself. (`OSW-2148 <https://rubinobs.atlassian.net//browse/OSW-2148>`_)


v0.5.12 (2026-02-10)
====================

Bug Fixes
---------

- Added cooperative task cancellation and avoid cancelling a task within its child. (`OSW-1787 <https://rubinobs.atlassian.net//browse/OSW-1787>`_)


v0.5.11 (2026-01-26)
====================

New Features
------------

- Allow disabling of wind, precipitation, humidity, and disable precipitation by default. (`OSW-769 <https://rubinobs.atlassian.net//browse/OSW-769>`_)
- Added telemetry associated with XML cycle 42. (`OSW-1138 <https://rubinobs.atlassian.net//browse/OSW-1138>`_)


Bug Fixes
---------

- Fixed problems that were causing faults in BTS. (`OSW-1160 <https://rubinobs.atlassian.net//browse/OSW-1160>`_)


Performance Enhancement
-----------------------

- Updated ts-conda-build dependency version and conda build string. (`OSW-1277 <https://rubinobs.atlassian.net//browse/OSW-1277>`_)


v0.5.10 (2025-07-23)
====================

Bug Fixes
---------

- Called super methods for asyncSetUp and asyncTearDown in testing. (`OSW-753 <https://rubinobs.atlassian.net//browse/OSW-753>`_)


v0.5.9 (2025-07-22)
===================

New Features
------------

- Add towncrier and fix versioning. (`OSW-730 <https://rubinobs.atlassian.net//browse/OSW-730>`_)


v0.5.2
======

* Added auto-reconnect.

v0.5.1
======

* Implemented the getNewDataProducts command.

v0.5.0
======

* Implemented the telemetry items.
* Added `alerts`, `errors`, `temperatureControl`, and `ups` events.

v0.4.0
======

* Modified the mock to better reflect the behavior of the real DREAM.
* Added use of setWeather to advise DREAM about current weather conditions.

v0.3.0
======

* Moved all python modules into the lsst.ts.dream.csc module.
* Added a lsst.ts.dream.common package in a dedicated repository and started using it.

Requires:

* ts-dream-common
* ts_salobj 6.5
* ts_idl 3.2
* IDL file for DREAM from ts_xml 9.1

v0.2.0
======

* Updated the CSC accordingly to changes in the ICD.
* Added documentation describing the communication protocols.

v0.1.0
======

First release of the DREAM CSC.

This version basically is an empty CSC to which functionality will be added at a later stage.

Requires:

* ts_salobj 6.3
* ts_idl 3.0
* IDL file for DREAM from ts_xml 8.2
