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

__all__ = ["DreamModel"]

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

from lsst.ts import tcpip, utils


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

        async with self.cmd_lock:
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

        request_id: int = next(self.index_generator)
        self.log.debug(f"Send: {command} {parameters}")
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
