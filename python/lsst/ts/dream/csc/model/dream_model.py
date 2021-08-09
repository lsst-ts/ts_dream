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
import json
import time
from typing import Any, Dict, List, Optional, Union

from lsst.ts import salobj, tcpip

"""Standard timeout in seconds for socket connections."""
SOCKET_TIMEOUT = 5


class DreamModel:
    """Utility class to handle all communication with the DREAM hardware.

    Parameters
    ----------
    log : `logging.Logger`, optional
        Logger or None. If None a logger is constructed, else a child to the
        provided logger is constructed.

    Attributes
    ----------
    reader: `asyncio.StreamReader`
        The stream reader to read from the TCP/IP socket.
    writer: `asyncio.StreamWriter`
        The stream writer to write to the TCP/IP socket.
    read_loop: `asyncio.Future`
        The loop that continuously reads from the TCP/IP socket.
    sent_commands: `List[int]`
        A list of command IDs that have been sent but not have been replied to
        yet.
    received_cmd_ids: `List[int]`
        A list of command IDs for which a reply has been received. This is used
        in unit tests.
    """

    def __init__(self, log: logging.Logger = None) -> None:
        if log is None:
            self.log = logging.getLogger(type(self).__name__)
        else:
            self.log = log.getChild(type(self).__name__)
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.read_loop: Optional[asyncio.Future] = None
        self.sent_commands: List[int] = []
        self.received_cmd_ids: List[int] = []
        self.index_generator = salobj.index_generator()

    async def connect(self, host: str, port: int) -> None:
        """Connect to the server.

        Parameters
        ----------
        host: `str`
            The host to connect to.
        port: `int
            The port to connect to.
        """
        rw_coro = asyncio.open_connection(host=host, port=port)
        self.reader, self.writer = await asyncio.wait_for(
            rw_coro, timeout=SOCKET_TIMEOUT
        )
        # Start a loop to read incoming data from the SocketServer.
        self.read_loop = asyncio.create_task(self._read_loop())

    async def read(self) -> dict:
        """Utility function to read a string from the reader and unmarshal it

        Returns
        -------
        data: `dict`
            A dictionary with objects representing the string read.
        """
        if not self.reader or not self.connected:
            raise RuntimeError("Not connected")

        read_bytes = await asyncio.wait_for(
            self.reader.readuntil(tcpip.TERMINATOR), timeout=SOCKET_TIMEOUT
        )
        data = json.loads(read_bytes.decode())
        return data

    async def write(self, command: str, **data: Any) -> None:
        """Write the command and data appended with a newline character.

        Parameters
        ----------
        command: `str`
            The command to write.
        data: `dict`
            The data to write.

        Raises
        ------
        RuntimeError
            In case there is no socket connection to a server.
        """
        if not self.writer or not self.connected:
            raise RuntimeError("Not connected")

        cmd_id: int = next(self.index_generator)
        time_command_sent: float = time.time()
        st = json.dumps(
            {
                "command": command,
                "cmd_id": cmd_id,
                "time_command_sent": time_command_sent,
                **data,
            }
        )
        self.writer.write(st.encode() + tcpip.TERMINATOR)
        await self.writer.drain()
        self.sent_commands.append(cmd_id)

    async def _read_loop(self) -> None:
        """Execute a loop that reads incoming data from the SocketServer."""
        try:
            while True:
                data = await self.read()
                self.log.info(f"Received data {data!r}")
                if "cmd_id" in data:
                    if not data["cmd_id"] in self.sent_commands:
                        self.log.error(
                            f"Received a reply to an unknown cmd ID {data['cmd_id']}."
                        )
                    else:
                        # TODO Properly handle command execution tracing.
                        self.received_cmd_ids.append(data["cmd_id"])
                        self.sent_commands.remove(data["cmd_id"])
                else:
                    # TODO implement handling of messages from DREAM
                    pass
        except Exception:
            self.log.exception("_read_loop failed")

    async def disconnect(self) -> None:
        """Disconnect, if connected."""
        self.log.info("Disconnecting")

    @property
    def connected(self) -> bool:
        return not (
            self.reader is None
            or self.writer is None
            or self.reader.at_eof()
            or self.writer.is_closing()
        )

    async def resume(self) -> None:
        await self.write(command="resume")

    async def open_hatch(self) -> None:
        await self.write(command="openHatch")

    async def close_hatch(self) -> None:
        await self.write(command="closeHatch")

    async def stop(self) -> None:
        await self.write(command="stop")

    async def ready_for_data(self, ready: bool) -> None:
        await self.write(command="readyForData", parameters={"ready": ready})

    async def data_archived(self) -> None:
        await self.write(command="dataArchived")

    async def set_weather_info(
        self, weather_info: Dict[str, Union[bool, float]]
    ) -> None:
        await self.write(
            command="setWeatherInfo", parameters={"weather_info": weather_info}
        )
