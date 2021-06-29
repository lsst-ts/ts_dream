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
import json
import logging
import time
import unittest

from lsst.ts import tcpip
from lsst.ts.dream.mock.mock_dream import MockDream

logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)

"""Standard timeout in seconds."""
TIMEOUT = 5


class MockDreamTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ctrl = None
        self.writer = None
        self.mock_ctrl = None
        self.srv: MockDream = MockDream(host="0.0.0.0", port=0)

        self.log = logging.getLogger(type(self).__name__)

        await self.srv.start_task
        self.assertTrue(self.srv.server.is_serving())
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
            self.reader.readuntil(tcpip.TERMINATOR), timeout=TIMEOUT
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
        self.writer.write(st.encode() + tcpip.TERMINATOR)
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

    async def verify_command(self, command, parameters=None):
        self.assertTrue(self.srv.connected)
        cmd_id = 1
        time_command_sent = time.time()
        if parameters:
            await self.write(
                command=command,
                cmd_id=cmd_id,
                time_command_sent=time_command_sent,
                parameters=parameters,
            )
        else:
            await self.write(
                command=command,
                cmd_id=cmd_id,
                time_command_sent=time_command_sent,
            )
        # Give time to the socket server to process the command.
        await asyncio.sleep(0.5)
        data = await self.read()
        self.assertEqual(data["cmd_id"], cmd_id)
        self.assertGreater(data["time_command_received"], time_command_sent)
        self.assertGreater(data["time_ack_sent"], data["time_command_received"])
        self.assertEqual(data["response"], "OK")

    async def test_commands_without_params(self):
        for command in ["resume", "openHatch", "closeHatch", "stop", "dataArchived"]:
            await self.verify_command(command=command)

    async def test_ready_for_data(self):
        await self.verify_command(command="readyForData", parameters={"ready": False})

    async def test_set_weather_info(self):
        await self.verify_command(
            command="setWeatherInfo",
            parameters={
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
