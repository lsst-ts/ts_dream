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

__all__ = ["DreamCsc", "run_dream"]

import asyncio
from types import SimpleNamespace
from typing import Optional

from lsst.ts import salobj

from . import CONFIG_SCHEMA, __version__
from .model import DreamModel


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
        config_dir: str | None = None,
        initial_state: salobj.State = salobj.State.STANDBY,
        simulation_mode: int = 0,
        mock_port: int | None = None,
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
        self.mock_port: Optional[int] = mock_port
        self.model = DreamModel(log=self.log)

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

        host: str = self.config.host
        port: int = self.config.port
        if self.mock_port:
            port = self.mock_port
        await self.model.connect(host=host, port=port)

    async def begin_enable(self, id_data: salobj.BaseDdsDataType) -> None:
        """Begin do_enable; called before state changes.

        This method sends a CMD_INPROGRESS signal.

        Parameters
        ----------
        id_data: `CommandIdData`
            Command ID and data
        """
        await super().begin_enable(id_data)
        self.cmd_enable.ack_in_progress(id_data, timeout=60)

    async def end_enable(self, id_data: salobj.BaseDdsDataType) -> None:
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

    async def begin_disable(self, id_data: salobj.BaseDdsDataType) -> None:
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

    async def disconnect(self) -> None:
        """Disconnect the DREAM CSC, if connected."""
        self.log.info("Disconnecting")
        await self.model.disconnect()

    async def handle_summary_state(self) -> None:
        """Override of the handle_summary_state function to connect or
        disconnect to the DREAM CSC (or the mock client) when needed.
        """
        self.log.info(f"handle_summary_state {salobj.State(self.summary_state).name}")
        if self.disabled_or_enabled:
            if not self.connected:
                await self.connect()
        else:
            await self.disconnect()

    async def configure(self, config: SimpleNamespace) -> None:
        self.config = config

    @property
    def connected(self) -> bool:
        return not self.model.connected

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_ocs"

    async def do_pause(self, data: salobj.BaseMsgType) -> None:
        # To be implemented later.
        pass

    async def do_resume(self, data: salobj.BaseMsgType) -> None:
        # To be implemented later.
        pass


def run_dream() -> None:
    asyncio.run(DreamCsc.amain(index=None))
