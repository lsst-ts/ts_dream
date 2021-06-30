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

__all__ = ["DreamCsc"]

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any, Optional

from . import __version__, CONFIG_SCHEMA
from lsst.ts import salobj, tcpip

"""Standard timeout in seconds for socket connections."""
SOCKET_TIMEOUT = 5


class DreamCsc(salobj.ConfigurableCsc):
    """Commandable SAL Component for the DREAM.

    Parameters
    ----------
    config_dir: `string`
        The configuration directory
    initial_state: `salobj.State`
        The initial state of the CSC
    simulation_mode: `int`
        Simulation mode (1) or not (0)
    mock_port: `int`, optional
        The port that the mock DREAM will listen on. Ignored when
        simulation_mode == 0.
    """

    valid_simulation_modes = (0, 1)
    version = __version__

    def __init__(
        self,
        config_dir: str = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        simulation_mode: int = 0,
        mock_port: int = None,
    ) -> None:
        self.config: Optional[SimpleNamespace] = None
        self._config_dir = config_dir
        super().__init__(
            name="DREAM",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
        )
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.host: Optional[str] = None
        self.port: Optional[int] = None
        self.mock_port: Optional[int] = mock_port
        self.read_loop: asyncio.Future = salobj.make_done_future()

    async def connect(self) -> None:
        """Determine if running in local or remote mode and dispatch to the
        corresponding connect coroutine.

        Raises
        ------
        RuntimeError
            In case no configuration has been loaded or already connected.
        """
        self.log.info("Connecting")
        self.log.info(self.config)
        self.log.info(f"self.simulation_mode = {self.simulation_mode}")
        if not self.config:
            raise RuntimeError("Not yet configured")
        if self.connected:
            raise RuntimeError("Already connected")

        if not self.host:
            self.host = self.config.host
        if self.mock_port:
            self.port = self.mock_port
        if not self.port:
            self.port = self.config.port
        rw_coro = asyncio.open_connection(host=self.host, port=self.port)
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

        cmd_id: int = salobj.index_generator()
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

    async def _read_loop(self) -> None:
        """Execute a loop that reads incoming data from the SocketServer."""
        try:
            while True:
                data = await self.read()
                self.log.info(f"Received data {data!r}")
        except Exception:
            self.log.exception("_read_loop failed")

    async def begin_enable(self, id_data) -> None:
        """Begin do_enable; called before state changes.

        This method sends a CMD_INPROGRESS signal.

        Parameters
        ----------
        id_data: `CommandIdData`
            Command ID and data
        """
        await super().begin_enable(id_data)
        self.cmd_enable.ack_in_progress(id_data, timeout=60)

    async def end_enable(self, id_data) -> None:
        """End do_enable; called after state changes but before command
        acknowledged.

        This method connects to the ESS Instrument and starts it.

        Parameters
        ----------
        id_data: `CommandIdData`
            Command ID and data
        """
        if not self.connected:
            await self.connect()
        await super().end_enable(id_data)

    async def begin_disable(self, id_data) -> None:
        """Begin do_disable; called before state changes.

        This method will try to gracefully stop the ESS Instrument and then
        disconnect from it.

        Parameters
        ----------
        id_data: `CommandIdData`
            Command ID and data
        """
        self.cmd_disable.ack_in_progress(id_data, timeout=60)
        await super().begin_disable(id_data)

    async def disconnect(self):
        """Disconnect the DREAM CSC, if connected."""
        self.log.info("Disconnecting")

    async def handle_summary_state(self):
        """Override of the handle_summary_state function to connect or
        disconnect to the DREAM CSC (or the mock client) when needed.
        """
        self.log.info(f"handle_summary_state {salobj.State(self.summary_state).name}")
        if self.disabled_or_enabled:
            if not self.connected:
                await self.connect()
        else:
            await self.disconnect()

    async def configure(self, config):
        self.config = config

    @property
    def connected(self) -> bool:
        return not (
            self.reader is None
            or self.writer is None
            or self.reader.at_eof()
            or self.writer.is_closing()
        )

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_ocs"
