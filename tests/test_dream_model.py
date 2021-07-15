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
import asyncio
import logging
import unittest

from lsst.ts import tcpip
from lsst.ts.dream.mock import MockDream
from lsst.ts.dream.model import DreamModel

logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)

"""Standard timeout in seconds."""
TIMEOUT = 5


class DreamModelTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.log = logging.getLogger(type(self).__name__)

        self.srv: MockDream = MockDream(host="0.0.0.0", port=0)
        await self.srv.start_task
        self.assertTrue(self.srv.server.is_serving())

        self.model = DreamModel(log=self.log)
        await self.model.connect(host=tcpip.LOCAL_HOST, port=self.srv.port)

    async def asyncTearDown(self):
        await self.model.disconnect()
        await self.srv.exit()

    async def validate_dream_model_func(self, func, **kwargs):
        self.assertTrue(len(self.model.sent_commands) == 0)
        self.assertTrue(len(self.model.received_cmd_ids) == 0)
        await func(**kwargs)
        self.assertTrue(len(self.model.sent_commands) == 1)
        self.assertTrue(len(self.model.received_cmd_ids) == 0)
        cmd_id = self.model.sent_commands[0]
        while len(self.model.sent_commands) > 0:
            await asyncio.sleep(0.1)
        self.assertTrue(len(self.model.sent_commands) == 0)
        self.assertTrue(len(self.model.received_cmd_ids) == 1)
        self.assertEqual(self.model.received_cmd_ids[0], cmd_id)

    async def test_functions_without_param(self):
        for func in [
            self.model.resume,
            self.model.open_hatch,
            self.model.close_hatch,
            self.model.stop,
            self.model.data_archived,
        ]:
            await self.validate_dream_model_func(func=func)
            self.model.received_cmd_ids = []

    async def test_ready_for_data(self):
        await self.validate_dream_model_func(func=self.model.ready_for_data, ready=True)

    async def test_set_weather_info(self):
        await self.validate_dream_model_func(
            func=self.model.set_weather_info,
            weather_info={
                "weather_info": {
                    "temperature": 5.7,
                    "humidity": 15,
                    "wind_speed": 12,
                    "wind_direction": 334,
                    "pressure": 101320,
                    "rain": 0,
                    "cloudcover": 0,
                    "safe_observing_conditions": True,
                }
            },
        )
