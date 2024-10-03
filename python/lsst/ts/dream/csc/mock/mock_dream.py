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
            "getStatus": self.get_status,
            "getNewDataProducts": self.get_new_data_products,
            "setWeather": self.set_weather,
            "setRoof": self.set_roof,
            "heartbeat": self.heartbeat,
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
                action = items["action"]
                request_id = items["request_id"]
                if action not in self.dispatch_dict:
                    await self.write(
                        {
                            "result": "error",
                            "reason": f"Unknown action {action}",
                        }
                    )
                else:
                    func = self.dispatch_dict[action]
                    result_json = await func(items["data"] if "data" in items else None)
                    await self.write(
                        result_json | {
                            "request_id": request_id,
                            "result": "ok",
                        }
                    )

            except KeyError as e:
                await self.write(
                    {
                        "result": "error",
                        "reason": f"Invalid request: a mandatory key is missing: {e.args[0]}",
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

    async def get_status(self, data: bool | None) -> dict:
        """Returns status information for DREAM.

        Parameters
        ----------
        data : bool | None
            Payload data sent to the command. This is
            ignored for this command, but providing
            extra data will not cause an error or
            any other change in behavior.

        Returns
        -------
        dict
            Data to be added to the response.
            The added data is a "msg_type",
            which is "status", and a summary
            dictionary.
        """
        self.log.info("get_status called.")

        return {
            "msg_type": "status",
            "status": dict(),
        }

    async def get_new_data_products(self, data: bool | None) -> dict:
        """Returns a list of new large files that are available.

        Provides a list of new files as a "new_products"
        key in the dictionary. This key contains a list
        of dictionaries, with one item on the list for
        each new file.

        Parameters
        ----------
        data : bool | None
            Payload data sent to the command. This is
            ignored for this command, but providing
            extra data will not cause an error or
            any other change in behavior.

        Returns
        -------
        dict
            Extra dictionary keys to be sent in
            the response. The added keys are
            "msg_type", which is "list",
            and "new_products", a list
            of zero or more dictionaries.
        """
        self.log.info("get_new_data_products called.")
        return {
            "msg_type": "list",
            "new_products": [],
        }

    async def set_weather(self, data: bool | None) -> dict:
        """Sets the weather status bit.

        If the payload data is True, then weather is OK
        and DREAM may observer. Otherwise DREAM should
        close down.

        Parameters
        ----------
        data : bool | None
            Whether the weather is OK for DREAM observing.
            Must be bool; failing to send data will
            return an error message.

        Returns
        -------
        dict
            Extra information to add to a success response.
            (But there is none in the case of this
            command, so it returns an empty dictionary.)
        """
        self.log.info("set_weather called.")
        return dict()

    async def set_roof(self, data: bool | None) -> dict:
        """Sets the roof status (open or closed)

        If the payload data is True, then the roof may open
        and DREAM may observe. If False, the roof should
        close.

        Parameters
        ----------
        data : bool | None
            Whether the roof may open. Bool is expected
            and setting data to None will send
            an error response back to the client.

        Returns
        -------
        dict[str, str]
            Extra information to add to a success response.
            (But there is none in the case of this
            command, so it returns an empty dictionary.)
        """
        self.log.info("set_roof called.")
        return dict()

    async def heartbeat(self, data: bool | None) -> dict:
        """Sends an empty response to the client.

        This function can be used to confirm that the server
        is still alive.

        Parameters
        ----------
        data : bool | None
            No data associated with this command. The argument
            is ignored, but extra data does not cause an error.

        Returns
        -------
        dict[str, str]
            Extra information to add to a success response.
            (But there is none in the case of this
            command, so it returns an empty dictionary.)
        """
        self.log.info("heartbeat called.")
        return dict()
