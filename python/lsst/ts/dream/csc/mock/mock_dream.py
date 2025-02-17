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

__all__ = ["MockDream"]

import asyncio
import json
import logging
import socket
import typing

from lsst.ts import tcpip

_dream_status = """
{
  "status": {
    "target_observing_mode": "IDLE",
    "actual_observing_mode": "IDLE",
    "target_dome_state": "STOP",
    "actual_dome_state": "STOP",
    "target_heater_state": "OFF",
    "actual_heater_state": "OFF",
    "target_peltier_state": "OFF",
    "actual_peltier_state": "OFF",
    "temp_hum": {
      "electronics_top": {
        "temperature": 25.76363921680424,
        "humidity": 50.671024074507606
      },
      "camera_bay": {
        "temperature": 25.960600848565594,
        "humidity": 50.380806542848525
      },
      "electronics_box": {
        "temperature": 25.842814592491973,
        "humidity": 50.311423547799194
      },
      "rack_top": {
        "temperature": 25.148454997628154,
        "humidity": 50.35500642777455
      },
      "rack_bottom": {
        "temperature": 25.177524512769548,
        "humidity": 50.548822284540506
      },
      "dream_inlet": {
        "temperature": 25.188939326407745,
        "humidity": 50.46328238367049
      }
    },
    "pdu_status": {
      "Switch": true,
      "USB hub": true,
      "PSU 1": true,
      "PSU 2": true,
      "Central Camera": true,
      "North Camera": true,
      "East Camera": true,
      "Command Server": true,
      "Central Server": true,
      "North Server": true,
      "East Server": true,
      "South Server": true,
      "West Server": true,
      "South Camera": true,
      "West Camera": true
    },
    "ups_status": {
      "ups_status": "ONLINE",
      "battery_charge": 100,
      "battery_temperature": 30.053783855218214,
      "battery_voltage": 48.95089981581298,
      "battery_remaining": 50,
      "battery_needs_replacing": false,
      "input_last_error": "no error",
      "output_load": 25.514144279491916,
      "output_current": 2.4332511053654104,
      "last_online": 1728426033.012355
    },
    "psu_status": {
      "temp_error": false,
      "input_error": false,
      "voltage_feedback": 0.04051622113408792,
      "current_feedback": 0.0008196898088569571,
      "voltage_setpoint": 0,
      "current_setpoint": 20
    },
    "limit_switches": {
      "front_door": "hit",
      "back_door": "hit",
      "dome_open": "not hit",
      "dome_closed": "not hit"
    },
    "electronics": {
      "motor_relay": "off",
      "motor_dir": "closing",
      "peltier_relay": "off",
      "peltier_dir": "heating",
      "window_heaters": "off"
    },
    "dome_position": 110,
    "errors": [
      "Dome should be closed but it is not",
      "Temp hum sensor not reachable",
      "PDU 2 not reachable"
    ],
    "warnings": [
      "North camera not connected",
      "East camera not connected",
      "South camera not connected",
      "Dome movements are simulated",
      "Temp/humidity sensors are simulated",
      "LEDs are simulated",
      "User stopped dome movement",
      "More than 1 client on rubin socket",
      "PDU is simulated",
      "West camera not connected",
      "Center camera not connected",
      "Dome opening blocked by sun alt",
      "UPS is simulated"
    ],
    "cameras": {}
  }
}
"""

_dream_new_data_products = """
[
  {
    "kind": "cloud",
    "type": "flat",
    "seq": [41, 51, 73],
    "start": "2025-02-14T21:02:55.206869",
    "end": "2025-02-14T22:49:02.688417",
    "server": "N",
    "size": 22,
    "filename": "product1.txt",
    "sha256": "23ff1547b9c233d672a844a319429224973d3d80f875db7e06c6264fb066d9a2"
  },
  {
    "kind": "cloud",
    "type": "science",
    "seq": [19, 36, 76, 76, 11, 56],
    "start": "2025-02-14T21:02:55.207006",
    "end": "2025-02-14T21:57:34.909060",
    "server": "W",
    "size": 22,
    "filename": "product2.txt",
    "sha256": "75aa4be4383599411fde6b3743175d0b644d9898e95aa00b3b312e3ad3256deb"
  },
  {
    "kind": "calibration",
    "type": null,
    "seq": [57, 6, 39, 47],
    "start": "2025-02-14T21:02:55.207107",
    "end": "2025-02-14T22:13:39.266971",
    "server": "S",
    "size": 22,
    "filename": "product3.txt",
    "sha256": "b0ecff2cf65ceda880023b5ccec025500afd313d9fdd5fc526ea37cc58c1823b"
  },
  {
    "kind": "image",
    "type": "bias",
    "seq": [17, 84, 12, 100, 10, 80],
    "start": "2025-02-14T21:02:55.207178",
    "end": "2025-02-14T21:59:03.871391",
    "server": "B",
    "size": 22,
    "filename": "product4.txt",
    "sha256": "26d360bc18c837220f338b03b66b8e1b6d751df475e9a453b87136a0bda4496b"
  }
]
"""


class MockDream(tcpip.OneClientServer):
    """A mock DREAM server for exchanging messages that talks over TCP/IP.

    Upon initiation a socket server is set up which waits for incoming
    commands.

    Parameters
    ----------
    host: `str` or `None`
        IP address for this server.
        If `None` then bind to all network interfaces.
    port: `int`
        IP port for this server. If 0 then use a random port.
    family: `socket.AddressFamily`, optional
        Address family for the socket connection, or socket.AF_UNSPEC.
    """

    def __init__(
        self,
        host: typing.Optional[str],
        port: int,
        family: socket.AddressFamily = socket.AF_UNSPEC,
        log: logging.Logger | None = None,
    ) -> None:
        self.name = "MockDream"
        self.read_loop_task: asyncio.Future = asyncio.Future()
        self.log: logging.Logger = (
            logging.getLogger(type(self).__name__) if log is None else log
        )

        # Dict of command: function to look up which funtion to call when a
        # command arrives.
        self.dispatch_dict: typing.Dict[str, typing.Callable] = {
            "getStatus": self.get_status,
            "getNewDataProducts": self.get_new_data_products,
            "setWeather": self.set_weather,
            "setRoof": self.set_roof,
            "heartbeat": self.heartbeat,
        }

        # Weather information data used for determining whether the hatch can
        # be opened or not.
        self.safe_observing_conditions: bool = False
        self.cloud_cover: int = 0

        super().__init__(
            name=self.name,
            host=host,
            port=port,
            log=self.log,
            connect_callback=self.connected_callback,
            family=family,
            terminator=b"\n",
        )

    async def connected_callback(self, server: tcpip.OneClientServer) -> None:
        """A client has connected or disconnected."""
        self.read_loop_task.cancel()
        if server.connected:
            self.log.info("Client connected.")
            self.read_loop_task = asyncio.create_task(self.read_loop())
        else:
            self.log.info("Client disconnected.")

    async def write_message(self, data: dict) -> None:
        """Write the data appended with a newline character.

        The data are encoded via JSON and then passed on to the StreamWriter
        associated with the socket.

        Parameters
        ----------
        data: `dict`
            The data to write.
        """
        self.log.debug(f"Writing data {data}")
        await self.write_json(data)

    async def read_loop(self: tcpip.OneClientServer) -> None:
        """Read commands and output replies."""
        self.log.debug(f"The read_loop begins connected? {self.connected}")
        while self.connected:
            self.log.debug("Waiting for next incoming message.")
            try:
                items = await self.read_json()
                action = items["action"]
                request_id = items["request_id"]
                if action not in self.dispatch_dict:
                    await self.write_message(
                        {
                            "request_id": request_id,
                            "result": "error",
                            "reason": f"Unknown action {action}",
                        }
                    )
                else:
                    func = self.dispatch_dict[action]
                    result_json = await func(items["data"] if "data" in items else None)
                    await self.write_message(
                        {
                            "request_id": request_id,
                            "result": "ok",
                            **result_json,
                        }
                    )

            except KeyError as e:
                await self.write_message(
                    {
                        "result": "error",
                        "reason": f"Invalid request: a mandatory key is missing: {e.args[0]}",
                    }
                )

            except asyncio.exceptions.IncompleteReadError:
                self.log.info(
                    "Read error encountered, probably because the connection was closed."
                )

            except Exception as ex:
                self.log.exception("Exception raised while preparing response.")
                await self.write_message(
                    {
                        "result": "error",
                        "reason": f"Exception: {ex!r}",
                    }
                )

    async def disconnect(self) -> None:
        """Disconnect the client."""
        await self.close_client()

    async def exit(self) -> None:
        """Stop the TCP/IP server."""
        self.log.info("Closing server")
        await self.close()
        self.log.info("Done closing")

    async def get_status(self, data: bool | None) -> dict:
        """Returns status information for DREAM.

        Parameters
        ----------
        data : bool | None
            Payload data sent to the command. This is
            ignored for this command, but providing
            extra data will not cause an error or
            any other change in behavior.

        Returns
        -------
        dict
            Data to be added to the response.
            The added data is a "msg_type",
            which is "status", and a summary
            dictionary.
        """
        self.log.info("get_status called.")

        return {
            "msg_type": "status",
            "status": json.loads(_dream_status)["status"],
        }

    async def get_new_data_products(self, data: bool | None) -> dict:
        """Returns a list of new large files that are available.

        Provides a list of new files as a "new_products"
        key in the dictionary. This key contains a list
        of dictionaries, with one item on the list for
        each new file.

        Parameters
        ----------
        data : bool | None
            Payload data sent to the command. This is
            ignored for this command, but providing
            extra data will not cause an error or
            any other change in behavior.

        Returns
        -------
        dict
            Extra dictionary keys to be sent in
            the response. The added keys are
            "msg_type", which is "list",
            and "new_products", a list
            of zero or more dictionaries.
        """
        self.log.info("get_new_data_products called.")
        return {
            "msg_type": "list",
            "new_products": json.loads(_dream_new_data_products),
        }

    async def set_weather(self, data: bool | None) -> dict:
        """Sets the weather status bit.

        If the payload data is True, then weather is OK
        and DREAM may observer. Otherwise DREAM should
        close down.

        Parameters
        ----------
        data : bool | None
            Whether the weather is OK for DREAM observing.
            Must be bool; failing to send data will
            return an error message.

        Returns
        -------
        dict
            Extra information to add to a success response.
            (But there is none in the case of this
            command, so it returns an empty dictionary.)
        """
        self.log.info("set_weather called.")
        if data is None:
            return {
                "result": "error",
                "reason": "data required",
            }
        return dict()

    async def set_roof(self, data: bool | None) -> dict:
        """Sets the roof status (open or closed)

        If the payload data is True, then the roof may open
        and DREAM may observe. If False, the roof should
        close.

        Parameters
        ----------
        data : bool | None
            Whether the roof may open. Bool is expected
            and setting data to None will send
            an error response back to the client.

        Returns
        -------
        dict[str, str]
            Extra information to add to a success response.
            (But there is none in the case of this
            command, so it returns an empty dictionary.)
        """
        self.log.info("set_roof called.")
        if data is None:
            return {
                "result": "error",
                "reason": "data required",
            }
        return dict()

    async def heartbeat(self, data: bool | None) -> dict:
        """Sends an empty response to the client.

        This function can be used to confirm that the server
        is still alive.

        Parameters
        ----------
        data : bool | None
            No data associated with this command. The argument
            is ignored, but extra data does not cause an error.

        Returns
        -------
        dict[str, str]
            Extra information to add to a success response.
            (But there is none in the case of this
            command, so it returns an empty dictionary.)
        """
        self.log.info("heartbeat called.")
        return dict()
