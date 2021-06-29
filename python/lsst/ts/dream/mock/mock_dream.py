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

__all__ = ["MockDream"]

import asyncio
import json
import logging
import socket
import time
import typing

from lsst.ts import tcpip


class MockDream(tcpip.OneClientServer):
    """A mock DREAM server for exchanging messages that talks over TCP/IP.

    Upon initiation a socket server is set up which waits for incoming
    commands.

    Parameters
    ----------
    host : `str` or `None`
        IP address for this server.
        If `None` then bind to all network interfaces.
    port : `int`
        IP port for this server. If 0 then use a random port.
    simulation_mode : `int`, optional
        Simulation mode. The default is 0: do not simulate.
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
            "openHatch": self.open_hatch,
            "closeHatch": self.close_hatch,
            "stop": self.stop,
            "readyForData": self.ready_for_data,
            "dataArchived": self.data_archived,
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

    def connected_callback(self, server) -> None:
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
        self.writer.write(st.encode() + tcpip.TERMINATOR)
        await self.writer.drain()
        self.log.debug("Done")

    async def read_loop(self: tcpip.OneClientServer) -> None:
        """Read commands and output replies."""
        try:
            self.log.info(f"The read_loop begins connected? {self.connected}")
            while self.connected:
                self.log.debug("Waiting for next incoming message.")
                try:
                    line = await self.reader.readuntil(tcpip.TERMINATOR)
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

        except Exception:
            self.log.exception("read_loop failed")

    async def disconnect(self) -> None:
        """Disconnect the client."""
        await self.close_client()

    async def exit(self) -> None:
        """Stop the TCP/IP server."""
        self.log.info("Closing server")
        await self.close()
        self.log.info("Done closing")

    async def resume(self):
        """Indicate that DREAM is permitted to resume automated operations."""
        self.log.info("resume called.")

    async def open_hatch(self):
        """Open the hatch if DREAM has evaluated that it is safe to do so."""
        self.log.info("open called.")

    async def close_hatch(self):
        """Close the hatch."""
        self.log.info("close called.")

    async def stop(self):
        """Immediately stop operations and close the hatch."""
        self.log.info("stop called.")

    async def ready_for_data(self, ready: bool):
        """Inform DREAM that Rubin Observatory is ready to receive data as
        indicated.

        Parameters
        ----------
        ready: `bool`
            Rubin Observatory is ready to receive data (True) or not (False).
        """
        self.log.info(f"readyForData called with param ready {ready}")

    async def data_archived(self):
        """Inform DREAM that Rubin Observatory has received and archived a data
        product."""
        self.log.info("dataArchived called.")

    async def set_weather_info(
        self, weather_info: typing.Dict[str, typing.Union[float, int, bool]]
    ):
        """Provide the latest weather information from Rubin Observatory.

        Parameters
        ----------
        weather_info: `dict`
            The weather info as provided by Rubin Observatory. The contents are

            - temperature: `float` (ºC)
            - humidity: `int` (0 - 100%)
            - wind_speed: `int` (m/s)
            - wind_direction: `int` (0 - 360º azimuth)
            - pressure: `int` (Pa)
            - rain: `int` (>= 0 mm)
            - cloudcover: `int` (0 - 100%)
            - safe_observing_conditions: `bool` (True or False)

        """
        self.log.info(f"setWeatherInfo called with param weather_info {weather_info}")
