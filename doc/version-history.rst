.. _version_history:Version_History:

###############
Version History
###############

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
