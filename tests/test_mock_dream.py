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

import asyncio
import json
import logging
import random
import unittest

from lsst.ts import tcpip
from lsst.ts.dream.csc.mock import MockDream

logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)

random.seed(42)

"""Standard timeout in seconds."""
TIMEOUT = 5

"""Line terminator for TCP. DREAM uses LF."""
TERMINATOR = b"\n"


class MockDreamTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.log = logging.getLogger(type(self).__name__)

        self.srv: MockDream = MockDream(host="0.0.0.0", port=0)
        await self.srv.start_task
        self.assertTrue(self.srv._server.is_serving())
        self.reader, self.writer = await asyncio.open_connection(
            host=tcpip.LOCAL_HOST, port=self.srv.port
        )

    async def asyncTearDown(self):
        await self.srv.disconnect()
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        await self.srv.exit()

    async def read(self):
        """Read a string from the reader and unmarshal it

        Returns
        -------
        data : `dict`
            A dictionary with objects representing the string read.
        """
        read_bytes = await asyncio.wait_for(
            self.reader.readuntil(TERMINATOR), timeout=TIMEOUT
        )
        data = json.loads(read_bytes.decode())
        return data

    async def write(self, **data):
        """Write the data appended with a TERMINATOR string.

        Parameters
        ----------
        data:
            The data to write.
        """
        st = json.dumps({**data})
        self.writer.write(st.encode() + TERMINATOR)
        await self.writer.drain()

    async def test_disconnect(self):
        self.assertTrue(self.srv.connected)
        await self.srv.disconnect()
        # Give time to the socket server to clean up internal state and exit.
        await asyncio.sleep(0.5)
        self.assertFalse(self.srv.connected)

    async def test_exit(self):
        self.assertTrue(self.srv.connected)
        await self.srv.exit()
        # Give time to the socket server to clean up internal state and exit.
        await asyncio.sleep(0.5)
        self.assertFalse(self.srv.connected)

    async def verify_command(self, action, **kwargs):
        self.assertTrue(self.srv.connected)
        request_id = 1
        await self.write(
            action=action,
            request_id=request_id,
            **kwargs,
        )
        # Give time to the socket server to process the command.
        await asyncio.sleep(0.5)
        data = await self.read()
        self.assertEqual(data["request_id"], request_id)
        self.assertEqual(data["result"], "ok")

    async def verify_error(self, action, **kwargs):
        self.assertTrue(self.srv.connected)
        request_id = random.randint(2, 5000)
        await self.write(action=action, request_id=request_id, **kwargs)
        # Give time to the socket server to process the command.
        await asyncio.sleep(0.5)
        data = await self.read()
        self.assertEqual(data["request_id"], request_id)
        self.assertEqual(data["result"], "error")

    async def test_commands_without_params(self):
        for action in [
            "getStatus",
            "getNewDataProducts",
            "setWeather",
            "setRoof",
            "heartbeat",
        ]:
            await self.verify_command(
                action=action, data=True
            )  # Some commands require "data".

    async def test_heartbeat(self):
        await self.verify_command(action="heartbeat")

    async def test_set_weather(self):
        await self.verify_error(action="setWeather")
        await self.verify_command(action="setWeather", data=True)
        await self.verify_command(action="setWeather", data=False)

    async def test_set_roof(self):
        await self.verify_error(action="setRoof")
        await self.verify_command(action="setRoof", data=True)
        await self.verify_command(action="setRoof", data=False)

    async def test_get_new_data_products(self):
        await self.verify_command(action="getNewDataProducts")

    async def test_get_status(self):
        await self.verify_command(action="getStatus")
