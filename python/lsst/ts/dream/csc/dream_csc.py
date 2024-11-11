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
import enum
import logging
import time
from types import SimpleNamespace

from lsst.ts import salobj, utils

from . import CONFIG_SCHEMA, __version__
from .mock import MockDream
from .model import DreamModel


class ErrorCode(enum.IntEnum):
    """CSC error codes."""

    TCPIP_CONNECT_ERROR = 1


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
        self.config: SimpleNamespace | None = None
        self._config_dir = config_dir

        self.mock: MockDream | None = None
        self.mock_port: int | None = mock_port

        # Remote CSC for the weather data.
        self.ess_remote: salobj.Remote | None = None
        self.weather_loop_task = utils.make_done_future()
        self.weather_sleep_task = utils.make_done_future()
        self.last_weather_update: float = 0.0
        self.weather_ok_flag: bool | None = None

        super().__init__(
            name="DREAM",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
        )

        ch = logging.StreamHandler()
        self.log.addHandler(ch)

        self.model: DreamModel | None = None

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

        if self.connected:
            self.log.warning("Not connecting because already connected.")
            return

        if not self.config:
            raise RuntimeError("Not yet configured")
        if self.connected:
            raise RuntimeError("Already connected")

        host: str = self.config.host
        port: int = self.config.port

        try:
            if self.simulation_mode == 1:
                if self.mock_port is None:
                    self.mock = MockDream(host="127.0.0.1", port=0)
                    await self.mock.start_task
                    port = self.mock.port
                    self.log.info(f"Mock started on port {port}")
                else:
                    port = self.mock_port
                    self.log.info(f"Using mock on port {port}")

            if self.model is None:
                self.model = DreamModel(config=self.config, log=self.log)
            await self.model.connect(host=host, port=port)

        except Exception as e:
            err_msg = f"Could not open connection to host={host}, port={port}: {e!r}"
            await self.fault(code=ErrorCode.TCPIP_CONNECT_ERROR, report=err_msg)
            return

        self.weather_loop_task = asyncio.ensure_future(self.weather_loop())

    async def end_enable(self, id_data: salobj.BaseDdsDataType) -> None:
        """End do_enable; called after state changes but before command
        acknowledged.

        This method connects to the DREAM Instrument and starts it.

        Parameters
        ----------
        id_data: `CommandIdData`
            Command ID and data
        """
        if not self.connected:
            await self.cmd_enable.ack_in_progress(data=id_data, timeout=10)
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
        await self.cmd_disable.ack_in_progress(id_data, timeout=10)
        await self.disconnect()
        await super().begin_disable(id_data)

    async def disconnect(self) -> None:
        """Disconnect the DREAM CSC, if connected."""
        if not self.config:
            raise RuntimeError("Not yet configured")

        self.log.info("Disconnecting")
        if self.model is not None:
            await self.model.disconnect()
        self.model = None
        if self.mock:
            await self.mock.close()
            self.mock = None

        self.weather_loop_task.cancel()
        await self.weather_loop_task

        if self.ess_remote is not None:
            await self.ess_remote.close()
            self.ess_remote = None

        self.log.info("Disconnected.")

    async def configure(self, config: SimpleNamespace) -> None:
        self.config = config

    @property
    def connected(self) -> bool:
        if self.model is None:
            return False
        return self.model.connected

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_ocs"

    async def do_pause(self, data: salobj.BaseMsgType) -> None:
        await self.disconnect()

    async def do_resume(self, data: salobj.BaseMsgType) -> None:
        if not self.connected:
            await self.connect()

    async def weather_loop(self) -> None:
        """Periodically check weather station, and send a flag if needed.

        A weather flag is sent when the weather has changed, or every ten
        minutes.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        while self.model is not None and self.model.connected:
            if self.simulation_mode == 0:
                if self.ess_remote is None:
                    self.ess_remote = salobj.Remote(
                        domain=self.domain, name="ESS", index=self.config.ess_index
                    )
                    await self.ess_remote.start_task
                    self.log.debug(f"Connected to ESS:{self.config.ess_index}.")

                    self.weather_ok_flag = None
                    self.last_weather_update = 0.0
                    if self.ess_remote is None:
                        self.log.error("Failed to connect to weather CSC.")
                        continue

                try:
                    # Get weather data.
                    weather_ok_flag = True
                    air_flow = await self.ess_remote.tel_airFlow.next(
                        flush=False, timeout=2
                    )
                    if air_flow is None or air_flow.speed > 25:
                        weather_ok_flag = False

                    precipitation = await self.ess_remote.evt_precipitation.get()
                    if precipitation is None or (
                        precipitation.raining or precipitation.snowing
                    ):
                        weather_ok_flag = False
                except Exception:
                    self.log.exception("Failed to read weather data from ESS.")
                    self.ess_remote = None
                    continue

            else:
                # In simulation mode, don't try to read the weather station.
                weather_ok_flag = True

            # Compare weather flag with cached value.
            time_since_last_update = time.time() - self.last_weather_update
            if (
                weather_ok_flag != self.weather_ok_flag
                or time_since_last_update > 60 * 10
            ):
                try:
                    # Send weather flag
                    if self.model is not None:
                        await self.model.set_weather_ok(weather_ok_flag)
                        self.last_weather_update = time.time()
                        self.weather_ok_flag = weather_ok_flag
                    else:
                        self.log.info(
                            "Weather loop ending because of TCP disconnection."
                        )
                        return
                except asyncio.CancelledError:
                    self.log.info("Weather loop ending because of asycio cancel.")
                    return
                except Exception:
                    self.log.exception("Failed to send weather flag!")

            # Sleep for a bit.
            try:
                await asyncio.sleep(self.config.poll_interval)
                await self.weather_sleep_task
            except asyncio.CancelledError:
                self.log.info("Weather loop ending because of asyncio cancel.")


def run_dream() -> None:
    asyncio.run(DreamCsc.amain(index=None))
