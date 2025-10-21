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
import io
import logging
import pathlib
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Union

import httpx
from lsst.ts import salobj, utils

from . import CONFIG_SCHEMA, __version__
from .mock import MockDream
from .model import DataProduct, DreamModel

SAL_TIMEOUT = 120.0
CSC_RESET_SLEEP_TIME = 180.0
RECONNECT_TIMEOUT = 180.0
MAXIMUM_RECONNECT_WAIT = 60.0
BASE_RECONNECT_WAIT = 10.0


class ErrorCode(enum.IntEnum):
    """CSC error codes."""

    TCPIP_CONNECT_ERROR = 1
    UPLOAD_DATA_PRODUCT_FAILED = 2
    WEATHER_CSC_ERROR = 3


class DreamCsc(salobj.ConfigurableCsc):
    """Commandable SAL Component for the DREAM.

    Parameters
    ----------
    config_dir : `string`
        The configuration directory
    initial_state : `salobj.State`
        The initial state of the CSC
    simulation_mode : `int`
        Simulation mode (1) or not (0)
    mock_port : `int`, optional
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
        override: str = "",
    ) -> None:
        self.config: SimpleNamespace | None = None
        self._config_dir = config_dir

        self.mock: MockDream | None = None
        self.mock_port: int | None = mock_port

        # Remote CSC for the weather data.
        self.weather_and_status_loop_task = utils.make_done_future()
        self.data_product_loop_task = utils.make_done_future()
        self.weather_ok_flag: bool | None = None

        super().__init__(
            name="DREAM",
            index=0,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            override=override,
        )

        self.model: DreamModel | None = None

        # LFA related configuration:
        self.s3bucket: salobj.AsyncS3Bucket | None = None  # Set by `connect`.
        self.s3bucket_name: str | None = None  # Set by `configure`.
        self.s3instance: str | None = None  # Set by `connect`.

        self.health_monitor_loop_task = utils.make_done_future()

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
            raise RuntimeError("Not connecting because already connected.")

        if not self.config:
            raise RuntimeError("Not yet configured")

        # Set up the S3 bucket.
        if self.s3bucket is None:
            domock = self.config.s3instance == "test"
            self.s3bucket = salobj.AsyncS3Bucket(
                name=self.s3bucket_name, domock=domock, create=domock
            )

        host: str = self.config.host
        port: int = self.config.port

        if self.simulation_mode == 1:
            if self.mock_port is None:
                self.mock = MockDream(host="127.0.0.1", port=0, log=self.log)
                await self.mock.start_task
                port = self.mock.port
                self.log.info(f"Mock started on port {port}")
            else:
                port = self.mock_port
                self.log.info(f"Using mock on port {port}")

        if self.model is None:
            self.model = DreamModel(config=self.config, log=self.log)
        await self.model.connect(host=host, port=port)

        self.weather_and_status_loop_task = asyncio.create_task(
            self.weather_and_status_loop()
        )
        self.health_monitor_loop_task = asyncio.create_task(self.health_monitor())
        if self.config.run_data_product_loop:
            self.data_product_loop_task = asyncio.create_task(self.data_product_loop())

    async def end_start(self, id_data: salobj.BaseMsgType) -> None:
        """End do_start; called after state changes but before command
        acknowledged.

        This method connects to the DREAM Instrument and starts it. It
        does not issue setRoof, because that happens during enable.

        Parameters
        ----------
        id_data : `salobj.BaseMsgType`
            Command ID and data
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        if not self.connected:
            await self.cmd_enable.ack_in_progress(data=id_data, timeout=SAL_TIMEOUT)
            try:
                await self.connect()
            except Exception as e:
                err_msg = (
                    "Could not open connection to "
                    f"host={self.config.host}, port={self.config.port}: {e!r}"
                )
                self.log.exception(err_msg)
                await self.fault(code=ErrorCode.TCPIP_CONNECT_ERROR, report=err_msg)

        await super().end_start(id_data)

    async def end_enable(self, id_data: salobj.BaseMsgType) -> None:
        """End do_enable; called after state changes but before command
        acknowledged.

        This method issues setRoof open to DREAM.

        Parameters
        ----------
        id_data : `salobj.BaseMsgType`
            Command ID and data
        """
        if self.model is None:
            raise RuntimeError("No model connected.")

        await self.model.open_roof()
        await super().end_enable(id_data)

    async def begin_standby(self, id_data: salobj.BaseMsgType) -> None:
        """Begin do_standby; called before state changes.

        This method will try to gracefully stop the ESS Instrument and then
        disconnect from it, and disconnect from the DREAM TCP server.

        Parameters
        ----------
        id_data : `salobj.BaseMsgType`
            Command ID and data
        """
        await self.cmd_standby.ack_in_progress(id_data, timeout=SAL_TIMEOUT)
        await self.stop_health_monitor_and_disconnect()
        await super().begin_standby(id_data)

    async def begin_disable(self, id_data: salobj.BaseMsgType) -> None:
        """Begin do_disable; called before state changes.

        This method will close the roof with the setRoof command.

        Parameters
        ----------
        id_data : `CommandIdData`
            Command ID and data
        """
        if self.model is None:
            raise RuntimeError("No model connected.")

        await self.model.close_roof()
        await super().begin_disable(id_data)

    async def disconnect(self, close_roof: bool = True) -> None:
        """Disconnect the DREAM CSC, if connected.

        Parameters
        ----------
        close_roof : bool
            Should a command be sent to close the roof before disconnecting?
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        self.log.info("Disconnecting")

        # End the monitor loops.
        self.weather_and_status_loop_task.cancel()
        self.data_product_loop_task.cancel()
        await asyncio.gather(
            self.weather_and_status_loop_task,
            self.data_product_loop_task,
            return_exceptions=True,
        )

        if self.model is not None:
            if close_roof:
                try:
                    await self.model.close_roof()
                except Exception:
                    self.log.exception("While disconnecting, failed to close the roof.")
            await self.model.disconnect()
        self.model = None
        if self.mock:
            await self.mock.close()
            self.mock = None

        self.log.info("Disconnected.")

    async def configure(self, config: SimpleNamespace) -> None:
        self.config = config
        self.s3bucket_name = salobj.AsyncS3Bucket.make_bucket_name(
            s3instance=config.s3instance,
        )

    async def health_monitor(self) -> None:
        """This loop monitors the health of the DREAM controller and the status
        and data product loops. If an issue happens it will disconnect and
        reconnect. If unable to reconnect, it will FAULT the CSC.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        while True:
            if self.weather_and_status_loop_task.done():
                if (exc := self.weather_and_status_loop_task.exception()) is not None:
                    self.log.exception(
                        "Weather and status loop health monitor tripped.", exc_info=exc
                    )
                else:
                    self.log.warning("Weather and status loop health monitor tripped.")
                break
            if self.config.run_data_product_loop and self.data_product_loop_task.done():
                if (exc := self.data_product_loop_task.exception()) is not None:
                    self.log.exception("Data product loop tripped.", exc_info=exc)
                else:
                    self.log.warning("Data product loop health monitor tripped.")
                break
            await asyncio.sleep(self.heartbeat_interval)

        # Begin the process of trying to reconnect.
        reconnect_time = time.time()
        await self.disconnect(close_roof=False)
        attempt_number = 0
        while (
            time.time() - reconnect_time < RECONNECT_TIMEOUT
            and self.summary_state != salobj.State.FAULT
        ):
            self.log.info("Disconnect detected. Attempting to reconnect...")
            try:
                attempt_number += 1
                await self.connect()
                self.log.info("Reconnected.")
                return  # A new health monitor was spawned by connect().
            except Exception as e:
                self.log.exception(f"Reconnection attempt failed: {e!r}")
                sleep_time = min(
                    MAXIMUM_RECONNECT_WAIT,
                    BASE_RECONNECT_WAIT * 2 ** (attempt_number - 1),
                )
                await asyncio.sleep(sleep_time)

        self.log.error("Failed to reconnect. Fault!")
        await self.fault(
            code=ErrorCode.TCPIP_CONNECT_ERROR,
            report=f"Reconnection attempt failed after {attempt_number} attempts.",
        )

    @property
    def connected(self) -> bool:
        if self.model is None:
            return False
        return self.model.connected

    @staticmethod
    def get_config_pkg() -> str:
        return "ts_config_ocs"

    async def close_tasks(self) -> None:
        await self.stop_health_monitor_and_disconnect()
        await super().close_tasks()

    async def handle_summary_state(self) -> None:
        if self.summary_state == salobj.State.FAULT:
            try:
                await self.stop_health_monitor_and_disconnect()
            except Exception:
                # Never mind, we gave it a try.
                self.exception("Failed to disconnect after FAULT")

    async def do_pause(self, data: salobj.BaseMsgType) -> None:
        await self.stop_health_monitor_and_disconnect()

    async def stop_health_monitor_and_disconnect(self) -> None:
        self.health_monitor_loop_task.cancel()
        try:
            await self.health_monitor_loop_task
        except asyncio.CancelledError:
            pass

        await self.disconnect()

    async def do_resume(self, data: salobj.BaseMsgType) -> None:
        if not self.connected:
            await self.connect()

    async def data_product_loop(self) -> None:
        """Periodically check DREAM for new data products.

        Send the getDataProducts command to DREAM. Based on the
        response, collect the images from DREAM's HTTP server
        and send them to LFA.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        while self.model is not None and self.model.connected:
            self.log.debug("Checking for new data products...")

            if self.model is not None:
                data_products = await self.model.get_new_data_products()
                for data_product in data_products:
                    self.log.debug(f"New data product: {data_product.filename}")
                    try:
                        await self.upload_data_product(data_product)
                    except Exception:
                        self.log.exception("Upload data product failed")

            await asyncio.sleep(self.config.poll_interval)

        if self.model is None:
            self.log.warning("Data product loop terminating: self.model is None")
        else:
            self.log.warning(f"Data product loop terminating: {self.model.connected=}")

    async def weather_and_status_loop(self) -> None:
        """Periodically check DREAM status and weather station and send a flag.

        A weather flag is sent when the weather has changed, or every ten
        minutes.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        ess_retries = 5

        async with salobj.Remote(
            domain=self.domain, name="ESS", index=self.config.ess_index
        ) as ess_remote:
            self.weather_ok_flag = None
            last_weather_ok_flag = None

            use_wind = self.config.weather_limits["use_wind"]
            use_humidity = self.config.weather_limits["use_humidity"]
            use_precipitation = self.config.weather_limits["use_precipitation"]

            # Wait for the CSC to establish its connection.
            await asyncio.sleep(BASE_RECONNECT_WAIT)

            while self.model is not None and self.model.connected:
                self.log.debug("Checking weather and DREAM status...")

                try:
                    # Get weather data.
                    current_time = utils.current_tai()
                    weather_ok_flag = True

                    if use_wind:
                        air_flow = await ess_remote.tel_airFlow.aget(
                            timeout=SAL_TIMEOUT,
                        )
                        air_flow_age = (
                            1_000_000
                            if air_flow is None
                            else current_time - air_flow.private_sndStamp
                        )
                        if (
                            air_flow is None
                            or air_flow.speed > 25
                            or air_flow_age > 300
                        ):
                            weather_ok_flag = False

                    if use_precipitation:
                        precipitation = await ess_remote.evt_precipitation.aget(
                            timeout=SAL_TIMEOUT
                        )
                        if precipitation is None or (
                            precipitation.raining or precipitation.snowing
                        ):
                            weather_ok_flag = False

                    if use_humidity:
                        humidity = await ess_remote.tel_relativeHumidity.aget(
                            timeout=SAL_TIMEOUT
                        )
                        humidity_age = (
                            1_000_000
                            if humidity is None
                            else current_time - humidity.private_sndStamp
                        )
                        if (
                            humidity is None
                            or humidity.relativeHumidityItem >= 90
                            or humidity_age > 300
                        ):
                            weather_ok_flag = False

                    if (
                        weather_ok_flag != last_weather_ok_flag
                    ) or self.log.isEnabledFor(logging.DEBUG):
                        weather_report = f"Weather report:  {weather_ok_flag=}"
                        if use_wind:
                            weather_report += f"\n{air_flow.speed=}\n{air_flow_age=}"
                        if use_humidity:
                            weather_report += (
                                f"\n{humidity.relativeHumidityItem=}\n{humidity_age=}"
                            )
                        if use_precipitation:
                            weather_report += (
                                f"\n{precipitation.raining=}\n{precipitation.snowing=}"
                            )

                    if weather_ok_flag != last_weather_ok_flag:
                        self.log.info(weather_report)
                    elif self.log.isEnabledFor(logging.DEBUG):
                        self.log.debug(weather_report)

                    last_weather_ok_flag = weather_ok_flag
                except Exception:
                    self.log.exception("Failed to read weather data from ESS.")
                    await asyncio.sleep(CSC_RESET_SLEEP_TIME)  # A little extra safety

                    ess_retries -= 1
                    if ess_retries == 0:
                        self.log.error(
                            "Unable to read weather data from ESS. Giving up."
                        )
                        await self.fault(
                            code=ErrorCode.WEATHER_CSC_ERROR,
                            report="Unable to read weather data from ESS.",
                        )
                        return

                    continue

                try:
                    # Send weather flag
                    if self.model is not None:
                        await self.model.set_weather_ok(weather_ok_flag)
                        self.weather_ok_flag = weather_ok_flag
                    else:
                        self.log.info(
                            "Weather loop ending because of TCP disconnection."
                        )
                        return
                except Exception:
                    self.log.exception("Failed to send weather flag!")
                    raise

                try:
                    # Get status information and emit telemetry.
                    try:
                        status_data = await self.model.get_status()
                        await self.send_telemetry(status_data)
                        await self.send_events(status_data)

                    except KeyError:
                        self.log.exception("Status had unexpected format!")
                        raise
                except Exception:
                    self.log.exception("Failed to get DREAM status!")
                    raise

                # Sleep for a bit.
                try:
                    await asyncio.sleep(self.config.poll_interval)
                except asyncio.CancelledError:
                    self.log.info("Weather loop ending because of asyncio cancel.")
                    raise

    async def send_telemetry(self, status_data: dict[str, Any]) -> None:
        """Sends telemetry from the CSC based on status information.

        Extracts relevant data from the status structure returned
        from DREAM by the getStatus command and emits SAL telemetry.

        Parameters
        ----------
        status_data : `dict[str, Any]`
            The status structure returned by DREAM's getStatus
            command.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        try:
            environment_key_names = [
                "camera_bay",
                "electronics_box",
                "rack_top",
            ]

            # Dome telemetry...
            dome_encoder = status_data["dome_position"]
            await self.tel_dome.set_write(encoder=dome_encoder)

            # Environment telemetry...
            environment_temperature = [
                status_data["temp_hum"][key_name]["temperature"]
                for key_name in environment_key_names
            ]
            environment_humidity = [
                status_data["temp_hum"][key_name]["humidity"]
                for key_name in environment_key_names
            ]
            await self.tel_environment.set_write(
                temperature=environment_temperature,
                humidity=environment_humidity,
            )

            # Power supply telemetry...
            power_supply_voltage = [
                status_data["psu_status"]["voltage_feedback"],
                status_data["psu_status"]["voltage_setpoint"],
            ]
            power_supply_current = [
                status_data["psu_status"]["current_feedback"],
                status_data["psu_status"]["current_setpoint"],
            ]
            await self.tel_powerSupply.set_write(
                voltage=power_supply_voltage,
                current=power_supply_current,
            )

            # UPS telemetry...
            ups_battery_charge = status_data["ups_status"]["battery_charge"]
            await self.tel_ups.set_write(batteryCharge=ups_battery_charge)
        except KeyError:
            self.log.exception("Telemetry status from DREAM had unexpected format!")
            raise

    async def send_events(self, status_data: dict[str, Any]) -> None:
        """Emits events for the CSC based on status information.

        Extracts relevant data from the status structure returned
        from DREAM by the getStatus command and emits SAL events.

        Parameters
        ----------
        status_data : `dict[str, Any]`
            The status structure returned by DREAM's getStatus
            command.

        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        try:
            # Event `alerts`:
            # The DREAM team did not specify temperature or humidity limits
            # for DREAM operation, only wind and precipitation. So these are
            # always False.
            await self.evt_alerts.set_write(
                outsideHumidity=False,
                outsideTemperature=False,
            )

            # Event `errors`:
            pdu1_error = "PDU 1 not reachable"
            pdu2_error = "PDU 2 not reachable"
            temphum_error = "Temp hum sensor not reachable"
            camera_bay_temp_error = "Camera bay temperature too high"
            camera_bay_hum_error = "Humidity in camera bay too high"
            electronics_humidity_error = "Humidity in electronics box > limit"
            dome_humidity_error = "Humidity under dome > limit"
            dome_humidity_error_2 = "Humidty under dome > limit"

            error_flag_map = {
                "domeHumidity": [dome_humidity_error, dome_humidity_error_2],
                "enclosureTemperature": [camera_bay_temp_error],
                "enclosureHumidity": [camera_bay_hum_error],
                "electronicsBoxCommunication": [electronics_humidity_error],
                "temperatureSensorCommunication": [temphum_error],
                "domePositionUnknown": [],  # There seems to be no way of getting
                "daqCommunication": [],  # these errors from DREAM.
                "pduCommunication": [pdu1_error, pdu2_error],
            }

            error_dict: dict[str, Union[bool, list[bool]]] = {
                flag: any(
                    error_string in status_data["errors"]
                    for error_string in error_string_list
                )
                for flag, error_string_list in error_flag_map.items()
            }
            # DREAM does not provide separate information about each
            # temperature sensor, so we'll just duplicate the result
            # three times to provide the CSC with what it expects.
            error_dict["temperatureSensorCommunication"] = [
                bool(error_dict["temperatureSensorCommunication"])
            ] * 3
            await self.evt_errors.set_write(**error_dict)

            # Event `temperatureControl`:
            peltier_relay = status_data["electronics"]["peltier_relay"] == "on"
            peltier_direction = status_data["electronics"]["peltier_dir"]
            heating_on = peltier_relay and (peltier_direction == "heating")
            cooling_on = peltier_relay and (peltier_direction == "cooling")
            await self.evt_temperatureControl.set_write(
                heatingOn=heating_on,
                coolingOn=cooling_on,
            )

            # Event `ups`:
            ups_online = status_data["ups_status"]["ups_status"] == "ONLINE"
            ups_battery_low = (
                status_data["ups_status"]["battery_charge"]
                < self.config.battery_low_threshold
            )
            ups_not_on_mains = "UPS is on battery" in status_data["warnings"]
            ups_communication_error = (
                "UPS not reachable or not responding" in status_data["errors"]
            )
            await self.evt_ups.set_write(
                online=ups_online,
                batteryLow=ups_battery_low,
                notOnMains=ups_not_on_mains,
                communicationError=ups_communication_error,
            )

        except KeyError:
            self.log.exception("Events status from DREAM had unexpected format!")
            raise

    async def upload_data_product(self, data_product: DataProduct) -> None:
        """Retrieve a data file from DREAM and uploads it to LFA.

        Given a DataProduct structure transmitted from DREAM, pull
        the file from the specified URL on the DREAM's HTTP server,
        and then copy it to the LFA. If writing to the LFA fails,
        write the file to the local filesystem in the configured
        data product path directory (`self.config.data_product_path`)
        instead.

        Parameters
        ----------
        data_product: `DataProduct`
            Information about the new file that is available. This
            structure is sent by DREAM in response to the
            getNewDataProducts command.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        if not self.s3bucket:
            raise RuntimeError("S3 bucket not configured")

        if self.config.skip_tmpdata_products and data_product.filename.startswith(
            "/tmpdata/"
        ):
            self.log.debug(f"Skipping temporary data file {data_product.filename}")
            return

        # Set up an LFA bucket key
        product_type = "" if data_product.type is None else f"_{data_product.type}"

        start_time = datetime.fromtimestamp(data_product.start, tz=timezone.utc)
        start_time_str = start_time.isoformat(timespec="milliseconds").replace(
            "+00:00", ""
        )

        other = (
            f"{start_time_str}_{data_product.server}_"
            f"{data_product.kind}{product_type}_"
            f"{data_product.seq[0]:06d}_{data_product.seq[-1]:06d}"
            f"_r{data_product.revision}"
        )
        key = self.s3bucket.make_key(
            salname=self.salinfo.name,
            salindexname=None,
            generator="dream",
            date=start_time_str,
            other=other,
            suffix=pathlib.Path(data_product.filename).suffix,
        )

        if await self.s3bucket.exists(key):
            self.log.info(
                f"Skipping {key} because it already exists on S3. sha256={data_product.sha256}"
            )

        # Download the object with HTTP
        server = data_product.server
        if server not in self.config.data_product_host:
            raise RuntimeError(
                f"Unexpected data product server specified: {data_product.server}"
            )
        data_product_host = self.config.data_product_host[server]
        dream_url = f"http://{data_product_host}/{data_product.filename}"

        timeout = httpx.Timeout(300.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # First get the headers to check for redirect.
            head = await client.get(dream_url, follow_redirects=True)
            head.raise_for_status()
            dream_url = str(head.url)

            async with client.stream("GET", dream_url) as response:
                response.raise_for_status()

                try:
                    # First attempt: Save to S3
                    await self.save_to_s3(response, key)
                    return  # Success!
                except Exception as ex:
                    self.log.exception(
                        f"Could not upload {key} to S3: {ex!r}; trying to save to local disk."
                    )
                    await self.save_to_local_disk(response, key)

    async def save_to_s3(self, response: httpx.Response, key: str) -> None:
        """Upload file to S3 from an HTTP stream.

        Parameters
        ----------
        response : `httpx.Response`
            HTTP response object for the file to save.

        key : `str`
            S3 style filename key to save to.
        """
        if not self.s3bucket:
            raise RuntimeError("S3 bucket not configured")

        with io.BytesIO(await response.aread()) as buffer:
            await self.s3bucket.upload(fileobj=buffer, key=key)
        url = (
            f"{self.s3bucket.service_resource.meta.client.meta.endpoint_url}/"
            f"{self.s3bucket.name}/{key}"
        )
        await self.evt_largeFileObjectAvailable.set_write(
            url=url,
            generator="dream",
        )
        self.log.info(f"Successfully uploaded {key} to S3.")

    async def save_to_local_disk(self, response: httpx.Response, key: str) -> None:
        """Save the file from an HTTP stream to local disk.

        Parameters
        ----------
        response : `httpx.Response`
            HTTP response object for the file to save.

        key: `str`
            S3 style filename key to save to.
        """
        if not self.config:
            raise RuntimeError("Not yet configured")

        if not self.s3bucket:
            raise RuntimeError("S3 bucket not configured")

        filepath = (
            pathlib.Path(self.config.data_product_path) / self.s3bucket.name / key
        )
        dirpath = filepath.parent
        if not dirpath.exists():
            self.log.info(f"Creating directory {str(dirpath)}")
            dirpath.mkdir(parents=True, exist_ok=True)

        with open(filepath, "wb") as file:
            async for chunk in response.aiter_bytes():
                file.write(chunk)

        self.log.info(f"Saved {key} to local disk at {filepath}")


def run_dream() -> None:
    asyncio.run(DreamCsc.amain(index=None))
