# This file is part of ts_dream.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
    $schema: http://json-schema.org/draft-07/schema#
    $id: https://github.com/lsst-ts/ts_dream/blob/master/python/lsst/ts/dream/csc/config_schema.py
    # title must end with one or more spaces followed by the schema version, which must begin with "v"
    title: DREAM v6
    description: Schema for DREAM configuration files
    type: object
    properties:
      host:
        description: IP address of the TCP/IP interface
        type: string
        format: hostname
        default: "127.0.0.1"
      port:
        description: Port number of the TCP/IP interface
        type: integer
        default: 5000
      connection_timeout:
        description: Time limit for connecting to the TCP/IP interface (sec)
        type: number
        exclusiveMinimum: 0
        default: 10
      read_timeout:
        description: Time limit for reading data from the TCP/IP interface (sec)
        type: number
        exclusiveMinimum: 0
        default: 10
      poll_interval:
        description: Interval for polling the weather station (sec)
        type: number
        exclusiveMinimum: 0
        default: 10
      ess_index:
        description: Index for the ESS CSC to poll
        type: number
        minimum: 0
        default: 301
      battery_low_threshold:
        description: Percent charge on the UPS battery that is considered "low"
        type: number
        minimum: 0
        exclusiveMaximum: 100
        default: 25
      s3instance:
        description: >-
          Large File Annex S3 instance, for example "cp", "tuc" or  "ls".
        type: string
        pattern: "^[a-z0-9][.a-z0-9]*[a-z0-9]$"
      data_product_host:
        description: >
          Mapping of directions to servers where DREAM data are located.
          Each key corresponds to a direction (N, S, E, W, C) and maps to
          a hostname.
        type: object
        properties:
          N:
            type: string
          S:
            type: string
          E:
            type: string
          W:
            type: string
          C:
            type: string
          B:
            type: string
        required: [N, S, E, W, C, B]
        additionalProperties: false
      data_product_path:
        description: Local filesystem path for fallback storage of data products
        type: string
      run_data_product_loop:
        description: If true, the CSC should collect data products from DREAM
        type: boolean
      skip_tmpdata_products:
        description: >-
          If true, the CSC should not save data products from DREAM that have
          a file path starting with "/tmpdata/".
        type: boolean
    required:
      - host
      - port
      - connection_timeout
      - read_timeout
      - poll_interval
      - ess_index
      - battery_low_threshold
      - s3instance
      - data_product_host
      - data_product_path
      - run_data_product_loop
      - skip_tmpdata_products
    additionalProperties: false
    """
)
