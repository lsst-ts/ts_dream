#####
Dream
#####

.. update the following links to point to your CSC
.. image:: https://img.shields.io/badge/SAL-API-gray.svg
    :target: https://ts-xml.lsst.io/sal_interfaces/Dream.html
.. image:: https://img.shields.io/badge/GitHub-gray.svg
    :target: https://github.com/lsst-ts/ts_dream
.. image:: https://img.shields.io/badge/Jira-gray.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_dream
.. image:: https://img.shields.io/badge/Jenkins-gray.svg
    :target: https://tssw-ci.lsst.org/job/LSST_Telescope-and-Site/job/ts_dream/

.. TODO: Delete the note when the page becomes populated

.. Warning::

   **This CSC documentation is under development and not ready for active use.**

.. _Overview:

Overview
========

Controller for the DREAM (Dutch Rubin Enhanced Atmospheric Monitor) system at Vera C. Rubin Observatory.

As with all CSCs, information on the package, developers and product owners can be found in the `Master CSC Table <ts_xml:index:master-csc-table:Dream>`_.

.. note:: If you are interested in viewing other branches of this repository append a `/v` to the end of the url link. For example `https://ts_dream.lsst.io/v/`


.. _User_Documentation:

User Documentation
==================

The primary class is:

* `DreamCsc`: controller for the DREAM system.

Run the ``DREAM`` controller  using ``bin/run_dream.py``.

User-level documentation, found at the link below, is aimed at personnel looking to perform the standard use-cases/operations with the Dream.

.. toctree::
    user-guide/user-guide
    :maxdepth: 2

.. _Configuration:

Configuring the Dream
=====================

The configuration for the Dream is described at the following link.

.. toctree::
    configuration/configuration
    :maxdepth: 1


.. _Development_Documentation:

Development Documentation
=========================

This area of documentation focuses on the classes used, API's, and how to participate to the development of the Dream software packages.

.. toctree::
    developer-guide/developer-guide
    :maxdepth: 1

.. _Version_History:

Version History
===============

The version history of the Dream is found at the following link.

.. toctree::
    version-history
    :maxdepth: 1
