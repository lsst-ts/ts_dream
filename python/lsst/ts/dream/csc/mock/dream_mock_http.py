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

import random

from aiohttp import web


class MockDreamHTTPServer:
    """A simple HTTP server for unit testing of DREAM."""

    def __init__(self, host: str = "localhost", port: int = 0):
        self.host = host
        self.port = port if port != 0 else random.randint(1024, 65535)
        self.app = web.Application()
        self.app.add_routes(
            [
                web.get("/product1.txt", self.handle_request),
                web.get("/product2.txt", self.handle_request),
                web.get("/product3.txt", self.handle_request),
                web.get("/product4.txt", self.handle_request),
            ]
        )
        self.runner = None
        self.files = {
            "/product1.txt": "This is data product 1",
            "/product2.txt": "This is data product 2",
            "/product3.txt": "This is data product 3",
            "/product4.txt": "This is data product 4",
        }

    async def handle_request(self, request: web.Request) -> web.Response:
        if request.path in self.files:
            return web.Response(
                text=self.files[request.path], content_type="text/plain"
            )
        return web.Response(status=404, text="File not found")

    async def start(self) -> None:
        """Start the HTTP server asynchronously."""
        self.runner = web.AppRunner(self.app)
        assert self.runner is not None
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self.runner:
            await self.runner.cleanup()
