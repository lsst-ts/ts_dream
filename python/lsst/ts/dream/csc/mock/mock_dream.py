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

__all__ = ["MockDream"]

import asyncio
import json
import logging
import socket
import time
import typing

from lsst.ts import tcpip
from lsst.ts.dream import common


class MockDream(tcpip.OneClientServer, common.AbstractDream):
    """A mock DREAM server for exchanging messages that talks over TCP/IP.

    Upon initiation a socket server is set up which waits for incoming
    commands.

    Parameters
    ----------
    host: `str` or `None`
        IP address for this server.
        If `None` then bind to all network interfaces.
    port: `int`
        IP port for this server. If 0 then use a random port.
    family: `socket.AddressFamily`, optional
        Address family for the socket connection, or socket.AF_UNSPEC.
    """

    def __init__(
        self,
        host: typing.Optional[str],
        port: int,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> None:
        self.name = "MockDream"
        self.read_loop_task: asyncio.Future = asyncio.Future()
        self.log: logging.Logger = logging.getLogger(type(self).__name__)

        # Dict of command: function to look up which funtion to call when a
        # command arrives.
        self.dispatch_dict: typing.Dict[str, typing.Callable] = {
            "resume": self.resume,
            "openRoof": self.open_roof,
            "closeRoof": self.close_roof,
            "stop": self.stop,
            "readyForData": self.set_ready_for_data,
            "dataArchived": self.set_data_archived,
            "setWeatherInfo": self.set_weather_info,
        }

        # Weather information data used for determining whether the hatch can
        # be opened or not.
        self.safe_observing_conditions: bool = False
        self.cloud_cover: int = 0

        super().__init__(
            name=self.name,
            host=host,
            port=port,
            log=self.log,
            connect_callback=self.connected_callback,
            family=family,
        )

    async def connected_callback(self, server: tcpip.OneClientServer) -> None:
        """A client has connected or disconnected."""
        self.read_loop_task.cancel()
        if server.connected:
            self.log.info("Client connected.")
            self.read_loop_task = asyncio.create_task(self.read_loop())
        else:
            self.log.info("Client disconnected.")

    async def write(self, data: dict) -> None:
        """Write the data appended with a newline character.

        The data are encoded via JSON and then passed on to the StreamWriter
        associated with the socket.

        Parameters
        ----------
        data: `dict`
            The data to write.
        """
        self.log.debug(f"Writing data {data}")
        st = json.dumps({**data})
        self.log.debug(st)
        self._writer.write(st.encode() + tcpip.TERMINATOR)
        await self._writer.drain()
        self.log.debug("Done")

    async def read_loop(self: tcpip.OneClientServer) -> None:
        """Read commands and output replies."""
        self.log.info(f"The read_loop begins connected? {self.connected}")
        while self.connected:
            self.log.debug("Waiting for next incoming message.")
            try:
                line = await self._reader.readuntil(tcpip.TERMINATOR)
                time_command_received = time.time()
                line = line.decode().strip()
                self.log.debug(f"Read command line: {line!r}")
                items = json.loads(line)
                cmd = items["command"]
                cmd_id = items["cmd_id"]
                # time_command_sent = items["time_command_sent"]
                kwargs = {}
                if "parameters" in items:
                    kwargs = items["parameters"]
                if cmd not in self.dispatch_dict:
                    raise KeyError(f"Invalid command {cmd} received.")
                else:
                    func = self.dispatch_dict[cmd]
                    await func(**kwargs)
                    await self.write(
                        {
                            "cmd_id": cmd_id,
                            "time_command_received": time_command_received,
                            "time_ack_sent": time.time(),
                            "response": "OK",
                        }
                    )

            except asyncio.IncompleteReadError:
                self.log.exception("Read error encountered. Retrying.")

    async def disconnect(self) -> None:
        """Disconnect the client."""
        await self.close_client()

    async def exit(self) -> None:
        """Stop the TCP/IP server."""
        self.log.info("Closing server")
        await self.close()
        self.log.info("Done closing")

    async def resume(self) -> None:
        """Indicate that DREAM is permitted to resume automated operations."""
        self.log.info("resume called.")

    async def open_roof(self) -> None:
        """Open the hatch if DREAM has evaluated that it is safe to do so."""
        self.log.info("open called.")

    async def close_roof(self) -> None:
        """Close the hatch."""
        self.log.info("close called.")

    async def stop(self) -> None:
        """Immediately stop operations and close the hatch."""
        self.log.info("stop called.")

    async def set_ready_for_data(self, ready: bool) -> None:
        """Inform DREAM that Rubin Observatory is ready to receive data as
        indicated.

        Parameters
        ----------
        ready: `bool`
            Rubin Observatory is ready to receive data (True) or not (False).
        """
        self.log.info(f"readyForData called with param ready {ready}")

    async def set_data_archived(self) -> None:
        """Inform DREAM that Rubin Observatory has received and archived a data
        product."""
        self.log.info("dataArchived called.")

    async def set_weather_info(
        self, weather_info: typing.Dict[str, typing.Union[float, bool]]
    ) -> None:
        """Provide the latest weather information from Rubin Observatory.

        Parameters
        ----------
        weather_info: `dict`
            The weather info as provided by Rubin Observatory. The contents are

            - temperature: `float` (ºC)
            - humidity: `float` (0 - 100%)
            - wind_speed: `float` (m/s)
            - wind_direction: `float` (0 - 360º azimuth)
            - pressure: `float` (Pa)
            - rain: `float` (>= 0 mm)
            - cloudcover: `float` (0 - 100%)
            - safe_observing_conditions: `bool` (True or False)

        """
        self.log.info(f"setWeatherInfo called with param weather_info {weather_info}")

    async def status(self) -> None:
        """Send the current status of DREAM."""
        self.log.info("status called.")

    async def new_data_products(self) -> None:
        """Inform the client that new data products are available."""
        self.log.info("new_data_products called.")
