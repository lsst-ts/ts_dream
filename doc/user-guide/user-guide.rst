.. |CSC_developer| replace::  *Wouter van Reeven <wvanreeven@lsst.org>*
.. |CSC_product_owner| replace:: *Patrick Ingraham <pingraham@lsst.org>*

.. _User_Guide:

################
Dream User Guide
################

.. image:: https://img.shields.io/badge/GitHub-ts_dream-green.svg
    :target: https://github.com/lsst-ts/ts_dream
.. image:: https://img.shields.io/badge/Jenkins-ts_dream-green.svg
    :target: https://tssw-ci.lsst.org/job/LSST_Telescope-and-Site/job/ts_dream/
.. image:: https://img.shields.io/badge/Jira-ts_dream-green.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_dream
.. image:: https://img.shields.io/badge/ts_xml-DREAM-green.svg
    :target: https://ts-xml.lsst.io/sal_interfaces/DREAM.html


XML location can be found at the top of the :doc:`top of this page </index>`.

DREAM consists of 5 CMOS cameras taking pictures of the sky at a specified cadence.
The pictures are converted into several data products of which the sky transparancy maps are of most interest to the Rubin Observatory project.
The cameras are controlled by a Linux server each and the Dream CSC communicates with these servers via socket connections.

The Dream CSC provides operational commands for commanding the Linux servers during an observing night as well as engineering commands for low-level access and maintenance of the DREAM system.
All commands include the following metadata

* command_id: the ID of the command (unsigned 32-bit int)
* time_command_sent: the UNIX timestamp when the command was sent (float)

If a command includes one or more parameters, then the parameters need to be sent with the parameters keyword.

All commands are acknowledged within 2 seconds by DREAM.

The acknowledgement metadata is as follows:

* command_id: the ID of the command (unsigned 32-bit int)
* time_command_received: the UNIX timestamp when the command was received (float)
* time_ack_sent: the UNIX timestamp when the acknowledgement was sent (float)
* response_code: one of OK, Error1, Error2, etc (TBD) (string)

The DREAM sends status telemetry at a configurable, regular interval between 1 and 5 seconds (TBD).
The contents of the status are yet to be defined.

New data products are announced via setNewDataProducts JSON telemetry messages.
The telemetry metadata is as follows

* amount: the number of new data products (unsigned int >= 1)
* metadata: array

The metadata array contains the following, mandatory items:

* name: the name of the data product (string)
* location: the location where the data product can be obtained from (string)
* timestamp: the UNIX timestamp when the image, on which the data was based, was taken (float)

Dream Interface
===============

The ICD (work in progress) can be found here

https://drive.google.com/file/d/10SGy_6t6IAMdYFAJb7st3vmo_38tM-Vw/view?usp=sharing

The operational commands are

* resume: Indicate that DREAM is permitted to resume automated operations
* openHatch: Open the hatch if DREAM has evaluated that it is safe to do so
* closeHatch: Close the hatch
* stop: Immediately stop operations and close the hatch
* readyForData: Inform DREAM that Rubin Observatory is ready to receive data with a True/False parameter
* dataArchived: Inform DREAM that Rubin Observatory has received and archived a data product
* setWeatherInfo: Provide the latest weather information from Rubin Observatory to DREAM in JSON format

The weather information contains the following items

* temperature (ºC)
* humidity (0 - 100%)
* wind_speed (m/s)
* wind_direction (0 - 360º azimuth)
* pressure (Pa)
* rain (>= 0 mm)
* cloudcover (0 - 100%)
* safe_observing_conditions (True or False)

The engineering commands are yet to be defined.

Example Use-Case
================

A code example for how to use the Dream CSC will follow.

Example Commands
================

The resume command looks as follows:

.. code-block:: js

  {
    "command": "resume",
    "cmd_id": 1,
    "time_command_sent": 1624997916.102829
  }

The readyForData command looks as follows:

.. code-block:: js

  {
    "command": "readyForData",
    "cmd_id": 1,
    "time_command_sent": 1624997916.102829
    "parameters": {
      "ready": False
    }
  }

Example Responses
=================

An OK response looks as follows:

.. code-block:: js

  {
    "cmd_id": 1,
    "time_command_received": 1624997916.102829,
    "time_ack_sent": 1624997916.102931,
    "response": "OK"
  }

Example Telemetry
=================

Telemetry examples will follow.
