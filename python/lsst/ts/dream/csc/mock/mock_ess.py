# This file is part of ts_dream.
#
# Developed for Vera C. Rubin Observatory Telescope and Site Systems.
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

__all__ = ["MockWeather"]

import asyncio

from lsst.ts import salobj


class MockWeather(salobj.BaseCsc):
    """A very limited fake weather CSC

    It emits tel_airflow, tel_relativeHumidity and evt_precipitation.

    Parameters
    ----------
    initial_state : `salobj.State` or `int` (optional)
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `State.STANDBY`, the default.
    """

    valid_simulation_modes = [0]
    version = "mock"

    def __init__(self, initial_state: salobj.State):
        super().__init__(
            name="ESS",
            index=301,
            initial_state=initial_state,
            allow_missing_callbacks=True,
        )
        self.telemetry_interval = 3  # seconds
        self.telemetry_task: asyncio.Future = asyncio.Future()

    async def start(self) -> None:
        await super().start()
        await self.evt_precipitation.set_write(
            sensorName="",
            raining=False,
            snowing=False,
            location="",
        )

    async def cancel_telemetry_task(self) -> None:
        self.telemetry_task.cancel()
        try:
            await self.telemetry_task
        except asyncio.CancelledError:
            pass

    async def close_tasks(self) -> None:
        await self.cancel_telemetry_task()
        await super().close_tasks()

    async def handle_summary_state(self) -> None:
        await super().handle_summary_state()
        if self.disabled_or_enabled:
            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry_loop())
        else:
            await self.cancel_telemetry_task()

    async def telemetry_loop(self) -> None:
        while True:
            await self.tel_relativeHumidity.set_write(
                sensorName="",
                timestamp=0,
                relativeHumidityItem=50,
                location="",
            )
            await self.tel_airFlow.set_write(
                sensorName="",
                timestamp=0,
                direction=0,
                directionStdDev=0,
                speed=1.23,
                speedStdDev=0,
                maxSpeed=0,
                location="",
            )
            await asyncio.sleep(self.telemetry_interval)
