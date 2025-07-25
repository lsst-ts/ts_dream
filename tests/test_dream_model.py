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

#  type: ignore

import logging
import unittest
from types import SimpleNamespace

from lsst.ts import tcpip
from lsst.ts.dream.csc.mock import MockDream
from lsst.ts.dream.csc.model import DreamModel

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
        self.assertTrue(self.srv._server.is_serving())

        config = SimpleNamespace()
        config.connection_timeout = 1
        config.read_timeout = 1

        self.model = DreamModel(config=config, log=self.log)
        await self.model.connect(host=tcpip.LOCAL_HOST, port=self.srv.port)

    async def asyncTearDown(self):
        await self.model.disconnect()
        await self.srv.exit()
        await super().asyncTearDown()

    async def validate_dream_model_func(self, func, **kwargs):
        await func(**kwargs)

    async def test_functions_without_param(self):
        for func in [
            self.model.open_roof,
            self.model.close_roof,
        ]:
            await self.validate_dream_model_func(func=func)

    async def test_set_weather_ok(self):
        await self.model.set_weather_ok(True)
        await self.model.set_weather_ok(False)

    async def test_get_status(self):
        status = await self.model.get_status()
        self.assertEqual(status["target_observing_mode"], "IDLE")

    async def test_get_products(self):
        products = await self.model.get_new_data_products()
        self.assertEqual(len(products), 4)
        self.assertEqual(products[0].filename, "product1.txt")
