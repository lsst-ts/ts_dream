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

__all__ = ["DataProduct", "DreamModel"]

import asyncio
import logging
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any, Literal, Type, TypeVar

from astropy.time import Time
from lsst.ts import tcpip, utils

T = TypeVar("T", bound="DataProduct")


@dataclass
class DataProduct:
    kind: Literal["cloud", "image", "calibration", "lightcurve"]
    type: Literal["dark", "flat", "bias", "science"] | None
    seq: list[int]
    start: Time
    end: Time
    server: Literal["N", "E", "S", "W", "C", "B"]
    size: int  # in bytes
    filename: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass to dictionary with time in ISO format."""
        data = asdict(self)
        data["start"] = self.start.iso
        data["end"] = self.end.iso
        return data

    @classmethod
    def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
        """Build a dataclass object from dictionary with time in ISO format."""
        data["start"] = Time(data["start"])
        data["end"] = Time(data["end"])
        return cls(**data)


class DreamModel:
    """Utility class to handle all communication with the DREAM hardware.

    Parameters
    ----------
    log : `logging.Logger`, optional
        Logger or None. If None a logger is constructed, else a child to the
        provided logger is constructed.
    """

    def __init__(
        self, config: SimpleNamespace, log: logging.Logger | None = None
    ) -> None:
        if log is None:
            self.log = logging.getLogger(type(self).__name__)
        else:
            self.log = log.getChild(type(self).__name__)

        self.client = tcpip.Client(host="", port=0, log=self.log)

        self.index_generator = utils.index_generator()
        self.cmd_lock = asyncio.Lock()
        self.config = config

    async def connect(self, host: str, port: int) -> None:
        """Connect to the server.

        Parameters
        ----------
        host: `str`
            The host to connect to.
        port: `int
            The port to connect to.
        """
        async with self.cmd_lock:
            self.client = tcpip.Client(
                host=host, port=port, log=self.log, terminator=b"\n"
            )
            await asyncio.wait_for(
                self.client.start_task, timeout=self.config.connection_timeout
            )
        self.log.debug("Connected to DREAM")

    async def read(self) -> dict:
        """Utility function to read a JSON object from the client

        Returns
        -------
        data: `dict`
            A dictionary with objects representing the string read.
        """
        if not self.connected:
            raise RuntimeError("Not connected")

        data = await asyncio.wait_for(
            self.client.read_json(), timeout=self.config.read_timeout
        )
        return data

    async def write(self, command: str, **parameters: Any) -> dict:
        """Write the command and data appended with a newline character.

        Parameters
        ----------
        command: `str`
            The command to write.
        parameters: `dict`
            The data to write.

        Returns
        -------
        dict
            The response data from DREAM.

        Raises
        ------
        RuntimeError
            In case there is no socket connection to a server.
        """
        if not self.connected:
            raise RuntimeError("Not connected")

        async with self.cmd_lock:
            request_id: int = next(self.index_generator)
            self.log.debug(f"Send: {command} {request_id=} {parameters}")
            await self.client.write_json(
                {"action": command, "request_id": request_id, **parameters}
            )

            response = await self.read()

        if "request_id" not in response:
            self.log.error("No request_id in response from DREAM")
            raise RuntimeError("No request_id in response from DREAM")
        if response["request_id"] != request_id:
            self.log.error(f"Received unexpected request_id: {response['request_id']}")
            raise RuntimeError(
                f"Received unexpected request_id: {response['request_id']}"
            )
        if "result" not in response:
            self.log.error("Required key 'result' not found in response from DREAM")
            raise RuntimeError("Required key 'result' not found in response from DREAM")
        if response["result"] != "ok":
            self.log.error(f"Error response from DREAM. Full response: {response}")
            raise RuntimeError(f"Error response from DREAM. Full response: {response}")

        return response

    async def disconnect(self) -> None:
        """Disconnect, if connected."""
        self.log.info("Disconnecting")
        await self.client.close()

    @property
    def connected(self) -> bool:
        return self.client.connected

    async def open_roof(self) -> None:
        await self.write(command="setRoof", data=True)

    async def close_roof(self) -> None:
        await self.write(command="setRoof", data=False)

    async def set_weather_ok(self, weather_ok: bool) -> None:
        await self.write(command="setWeather", data=weather_ok)

    async def get_status(self) -> dict[str, Any]:
        """Queries and returns status information from DREAM.

        This function sends the getStatus command to DREAM. It reads
        the status information and returns the full set of status data
        reported by DREAM.

        Returns
        -------
        dict[str, Any]
            A dictionary of status items for DREAM. The format is dictated
            by the DREAM software, but the keys are strings and currently
            (as of January 2025) the values are either string, float,
            boolean, list, or dictionary, with the structure and format
            getting somewhat complex. Note that only the status body of the
            response is returned, rather than the entire message with
            request_id and so forth.

        Raises
        ------
        RuntimeError
            If DREAM responds in an unexpected way.
        """
        response = await self.write(command="getStatus")
        if response["msg_type"] != "status":
            self.log.error(
                f"In getStatus, received unexpected message type: {response['msg_type']}"
            )
            raise RuntimeError(
                f"In getStatus, received unexpected message type: {response['msg_type']}"
            )
        if "status" not in response:
            self.log.error("Unexpected format for status message!")
            raise RuntimeError("Unexpected format for status message!")

        return response["status"]

    async def get_new_data_products(self) -> list[DataProduct]:
        """Queries whether new data products are available from DREAM.

        New data products are made available from DREAM via HTTP. A
        query with this command provides the URL and other metadata
        associated with these data products. The DREAM CSC should
        collect these products and load them to the LFA.

        Returns
        -------
        list[DataProduct]
            A list of new data product items reported by DREAM.

        Raises
        ------
        RuntimeError
            If DREAM responds in an unexpected way.
        """
        response = await self.write(command="getNewDataProducts")
        if response["msg_type"] != "list":
            self.log.error(
                f"In getStatus, received unexpected message type: {response['msg_type']}"
            )
            raise RuntimeError(
                f"In getStatus, received unexpected message type: {response['msg_type']}"
            )
        if "new_products" not in response:
            self.log.error("Unexpected format for getNewDataProducts message!")
            raise RuntimeError("Unexpected format for getNewDataProducts message!")
        return [DataProduct.from_dict(dp) for dp in response["new_products"]]
