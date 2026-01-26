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
import logging
import math
import pathlib
import unittest

import lsst.ts.dream.csc as dream_csc
from astropy.time import Time
from lsst.ts import salobj
from lsst.ts.dream.csc import MockWeather
from lsst.ts.dream.csc.mock.dream_mock_http import MockDreamHTTPServer
from lsst.ts.xml.enums.DREAM import (
    Camera,
    CameraServerMode,
    DomeState,
    DomeTargetState,
    Error,
    HeaterState,
    PeltierState,
    Warning,
    Weather,
)

STD_TIMEOUT = 20  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parent / "config"

logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)


def timestamp(timestamp_isot: str) -> float:
    return float(Time(timestamp_isot).unix_tai)


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()

        self.http_server = MockDreamHTTPServer(port=5001)
        await self.http_server.start()

        self.log = logging.getLogger("test")
        self.srv = dream_csc.mock.MockDream(
            host="0.0.0.0", port=0, log=logging.getLogger("mock")
        )
        await self.srv.start_task

        self.weather_csc = MockWeather(initial_state=salobj.State.ENABLED)
        await self.weather_csc.start_task

        self.mock_port = self.srv.port
        self.writer = None

    async def asyncTearDown(self):
        try:
            await self.weather_csc.cancel_telemetry_task()
            await self.weather_csc.close()

            await self.srv.disconnect()
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
            await self.srv.exit()
            await self.http_server.stop()

        except Exception:
            self.log.exception("exception in asyncTearDown")

        finally:
            await super().asyncTearDown()

    def basic_make_csc(
        self, initial_state, config_dir, simulation_mode, override="", **kwargs
    ):
        return dream_csc.DreamCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
            mock_port=self.mock_port,
            override=override,
        )

    async def test_standard_state_transitions(self):
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.check_standard_state_transitions(
                enabled_commands=(),
                skip_commands=(
                    "resume",
                    "openRoof",
                    "closeRoof",
                    "stop",
                    "readyForData",
                    "dataArchived",
                    "setWeatherInfo",
                    "pause",
                ),
            )

        await self.http_server.stop()

    async def test_version(self):
        logging.info("test_version")
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_sample(
                self.remote.evt_softwareVersions,
                cscVersion=dream_csc.__version__,
                subsystemVersions="",
            )

    async def test_disable(self):
        logging.info("test_dome_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.STANDBY,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            self.assertFalse(self.srv.roof)
            await self.remote.cmd_start.set_start()
            self.assertFalse(self.srv.roof)
            await self.remote.cmd_enable.set_start()
            self.assertTrue(self.srv.roof)  # setRoof=true should have been issued
            await self.remote.cmd_disable.set_start()
            self.assertFalse(self.srv.roof)
            await self.remote.cmd_standby.set_start()
            self.assertFalse(self.srv.roof)

    async def test_dome_telemetry(self):
        logging.info("test_dome_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            dome_telemetry = await self.remote.tel_dome.next(
                timeout=STD_TIMEOUT, flush=False
            )
            self.assertEqual(dome_telemetry.encoder, 110)

    async def test_environment_telemetry(self):
        logging.info("test_environment_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            environment_telemetry = await self.remote.tel_environment.next(
                flush=False, timeout=STD_TIMEOUT
            )

            temperature = [
                25.76363921680424,  # Electronics top
                25.960600848565594,  # Camera bay
                25.842814592491973,  # Electronics box
                25.148454997628154,  # Rack top
                25.177524512769548,  # Rack bottom
                25.188939326407745,  # DREAM inlet
            ]

            humidity = [
                50.671024074507606,  # Electronics top
                50.380806542848525,  # Camera bay
                50.311423547799194,  # Electronics box
                50.35500642777455,  # Rack top
                50.548822284540506,  # Rack bottom
                50.46328238367049,  # DREAM inlet
            ]

            for i in range(len(temperature)):
                self.assertAlmostEqual(
                    environment_telemetry.temperature[i],
                    temperature[i],
                    places=4,
                )
                self.assertAlmostEqual(
                    environment_telemetry.humidity[i], humidity[i], places=4
                )

    async def test_camera_telemetry(self):
        logging.info("test_camera_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            camera_telemetry = await self.remote.tel_camera.next(
                flush=False, timeout=STD_TIMEOUT
            )
            timestamps = [
                "2025-09-25T14:24:30.341",
                "2025-09-25T14:24:31.078",
                "2025-09-25T14:24:31.078",
            ]
            timestamps = [timestamp(t) for t in timestamps]
            timestamps = [
                timestamps[0],
                math.nan,
                timestamps[1],
                math.nan,
                timestamps[2],
            ]
            temperatures = [3.14, math.nan, 42.0, math.nan, 1729.0]

            for i in range(len(timestamps)):
                if math.isnan(
                    camera_telemetry.lastCameraHeartbeatTimestamp[i]
                ) and math.isnan(timestamps[i]):
                    continue
                self.assertAlmostEqual(
                    camera_telemetry.lastCameraHeartbeatTimestamp[i],
                    timestamps[i],
                    places=2,
                )

            for i in range(len(temperatures)):
                if math.isnan(camera_telemetry.ccdTemperature[i]) and math.isnan(
                    temperatures[i]
                ):
                    continue
                self.assertAlmostEqual(
                    camera_telemetry.ccdTemperature[i],
                    temperatures[i],
                    places=2,
                )

    async def test_power_supply_telemetry(self):
        logging.info("test_power_supply_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            power_supply_telemetry = await self.remote.tel_powerSupply.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertAlmostEqual(power_supply_telemetry.voltage[0], 0.0405, places=4)
            self.assertAlmostEqual(power_supply_telemetry.voltage[1], 0.0, places=4)
            self.assertAlmostEqual(
                power_supply_telemetry.current[0], 0.0008196, places=4
            )
            self.assertAlmostEqual(power_supply_telemetry.current[1], 20.0, places=4)

    async def test_ups_telemetry(self):
        logging.info("test_ups_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            ups_telemetry = await self.remote.tel_ups.next(
                timeout=STD_TIMEOUT,
                flush=False,
            )
            self.assertAlmostEqual(ups_telemetry.batteryCharge, 100.0)

    async def test_alerts_event(self):
        logging.info("test_alerts_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            alerts_event = await self.remote.evt_alerts.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertFalse(alerts_event.outsideHumidity)
            self.assertFalse(alerts_event.outsideTemperature)

    async def test_camera_event(self):
        logging.info("test_camera_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            # Check for three and exactly three events published.
            expected_events = {
                Camera.East: salobj.BaseMsgType(),
                Camera.North: salobj.BaseMsgType(),
                Camera.South: salobj.BaseMsgType(),
            }

            expected_events[Camera.East].source = Camera.East
            expected_events[Camera.East].cameraMode = CameraServerMode.Idle
            expected_events[Camera.East].nBlank = 101
            expected_events[Camera.East].nDark = 43
            expected_events[Camera.East].nBias = 41
            expected_events[Camera.East].nFlat = 38
            expected_events[Camera.East].nScience = 0
            expected_events[Camera.East].nMissed = 0
            expected_events[Camera.East].lastSequenceNumber = 62955554
            expected_events[Camera.East].lastTriggerTime = timestamp(
                "2025-09-25T09:52:42.496"
            )
            expected_events[Camera.East].lastImageTimingLatency = 0.003159
            expected_events[Camera.East].lastImageUSBLatency = 0.000259
            expected_events[Camera.East].lastImageArtificialLatency = (
                5.7220458984375e-06
            )
            expected_events[Camera.East].lastImageType = CameraServerMode.Bias
            expected_events[Camera.East].lastImagePixelMedian = 1004

            expected_events[Camera.North].source = Camera.North
            expected_events[Camera.North].cameraMode = CameraServerMode.Idle
            expected_events[Camera.North].nBlank = 101
            expected_events[Camera.North].nDark = 43
            expected_events[Camera.North].nBias = 41
            expected_events[Camera.North].nFlat = 39
            expected_events[Camera.North].nScience = 0
            expected_events[Camera.North].nMissed = 0
            expected_events[Camera.North].lastSequenceNumber = 62955554
            expected_events[Camera.North].lastTriggerTime = timestamp(
                "2025-09-25T09:52:42.496"
            )
            expected_events[Camera.North].lastImageTimingLatency = 0.003164
            expected_events[Camera.North].lastImageUSBLatency = 0.000252
            expected_events[Camera.North].lastImageArtificialLatency = (
                6.4373016357421875e-06
            )
            expected_events[Camera.North].lastImageType = CameraServerMode.Science
            expected_events[Camera.North].lastImagePixelMedian = 1015

            expected_events[Camera.South].source = Camera.South
            expected_events[Camera.South].cameraMode = CameraServerMode.Idle
            expected_events[Camera.South].nBlank = 123
            expected_events[Camera.South].nDark = 43
            expected_events[Camera.South].nBias = 41
            expected_events[Camera.South].nFlat = 39
            expected_events[Camera.South].nScience = 0
            expected_events[Camera.South].nMissed = 0
            expected_events[Camera.South].lastSequenceNumber = 62955554
            expected_events[Camera.South].lastTriggerTime = timestamp(
                "2025-09-25T09:52:42.496"
            )
            expected_events[Camera.South].lastImageTimingLatency = 0.003183
            expected_events[Camera.South].lastImageUSBLatency = 0.000239
            expected_events[Camera.South].lastImageArtificialLatency = (
                6.9141387939453125e-06
            )
            expected_events[Camera.South].lastImageType = CameraServerMode.Bias
            expected_events[Camera.South].lastImagePixelMedian = 993

            camera_events = [
                await self.remote.evt_camera.next(flush=False, timeout=STD_TIMEOUT)
                for _ in range(3)
            ]

            def validate_camera_event(
                actual: salobj.BaseMsgType, expected: salobj.BaseMsgType
            ) -> None:
                self.assertEqual(actual.source, expected.source)
                self.assertEqual(actual.cameraMode, expected.cameraMode)
                self.assertEqual(actual.nBlank, expected.nBlank)
                self.assertEqual(actual.nDark, expected.nDark)
                self.assertEqual(actual.nBias, expected.nBias)
                self.assertEqual(actual.nFlat, expected.nFlat)
                self.assertEqual(actual.nScience, expected.nScience)
                self.assertEqual(actual.nMissed, expected.nMissed)
                self.assertEqual(actual.lastSequenceNumber, expected.lastSequenceNumber)
                self.assertAlmostEqual(
                    actual.lastTriggerTime, expected.lastTriggerTime, places=3
                )
                self.assertAlmostEqual(
                    actual.lastImageTimingLatency, expected.lastImageTimingLatency
                )
                self.assertAlmostEqual(
                    actual.lastImageUSBLatency, expected.lastImageUSBLatency
                )
                self.assertAlmostEqual(
                    actual.lastImageArtificialLatency,
                    expected.lastImageArtificialLatency,
                )
                self.assertEqual(actual.lastImageType, expected.lastImageType)
                self.assertEqual(
                    actual.lastImagePixelMedian, expected.lastImagePixelMedian
                )

            for camera_event in camera_events:
                source = camera_event.source
                expected_event = expected_events[source]
                validate_camera_event(camera_event, expected_event)

            # Make sure no more (duplicate) events arrive
            await asyncio.sleep(self.csc.config.poll_interval + 1)
            self.assertIsNone(self.remote.evt_camera.get_oldest())

    async def test_errors_event(self):
        logging.info("test_errors_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            errors_event = await self.remote.evt_errors.next(
                flush=False, timeout=STD_TIMEOUT
            )

            # Based on the content of the status message
            # in the mock object.
            self.assertFalse(errors_event.domeHumidity)
            self.assertFalse(errors_event.enclosureTemperature)
            self.assertFalse(errors_event.enclosureHumidity)
            self.assertFalse(errors_event.electronicsBoxCommunication)
            self.assertTrue(errors_event.temperatureSensorCommunication[0])
            self.assertTrue(errors_event.temperatureSensorCommunication[1])
            self.assertTrue(errors_event.temperatureSensorCommunication[2])
            self.assertFalse(errors_event.domePositionUnknown)
            self.assertFalse(errors_event.daqCommunication)
            self.assertTrue(errors_event.pduCommunication)

    async def test_power_supply_event(self):
        logging.info("test_power_supply_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            power_supply_event = await self.remote.evt_powerSupply.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertFalse(power_supply_event.temperatureError)
            self.assertFalse(power_supply_event.inputVoltageError)

    async def test_set_roof_event(self):
        logging.info("test_set_roof_event_false")
        async with self.make_csc(
            initial_state=salobj.State.DISABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            # When CSC is disabled, the setRoof event should show False
            set_roof_event = await self.remote.evt_setRoof.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.remote.evt_setRoof.flush()
            self.assertFalse(set_roof_event.roof)

            await self.remote.cmd_enable.set_start()

            # When CSC is enabled, the setRoof event should show True
            set_roof_event = await self.remote.evt_setRoof.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertTrue(set_roof_event.roof)

    async def test_set_weather_event(self):
        logging.info("test_set_weather_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            set_weather_event = await self.remote.evt_setWeather.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.remote.evt_setWeather.flush()
            self.assertTrue(set_weather_event.weather)

            self.weather_csc.windspeed = 1000
            set_weather_event = await self.remote.evt_setWeather.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertFalse(set_weather_event.weather)

    async def test_status_event(self):
        logging.info("test_status_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            status_event = await self.remote.evt_status.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(status_event.observingMode, CameraServerMode.Idle)
            self.assertEqual(status_event.targetObservingMode, CameraServerMode.Auto)
            self.assertEqual(status_event.dome, DomeState.Open)
            self.assertEqual(status_event.targetDome, DomeTargetState.Stop)
            self.assertEqual(status_event.heater, HeaterState.Auto)
            self.assertEqual(status_event.targetHeater, HeaterState.Off)
            self.assertEqual(status_event.peltier, PeltierState.Heat)
            self.assertEqual(status_event.targetPeltier, PeltierState.Off)
            self.assertEqual(status_event.power, [True] * 14 + [False])
            self.assertEqual(status_event.relayState, [True, False, True, False, True])
            self.assertEqual(
                status_event.errorFlags,
                Error.DomeError | Error.TemphumError | Error.Pdu2Error,
            )
            self.assertEqual(
                status_event.warningFlags,
                Warning.DomeClosedBySun
                | Warning.DomeStopped
                | Warning.RubinMultipleClients
                | Warning.CameraNNotConnected
                | Warning.CameraSNotConnected
                | Warning.CameraENotConnected
                | Warning.CameraWNotConnected
                | Warning.CameraCNotConnected
                | Warning.SimulatedDome
                | Warning.SimulatedLeds
                | Warning.SimulatedUps
                | Warning.SimulatedPdu
                | Warning.SimulatedEnv,
            )
            self.assertEqual(
                status_event.additionalErrors, "extra error 1;extra error 2"
            )
            self.assertEqual(status_event.additionalWarnings, "")

    async def test_temperature_control_event(self):
        logging.info("test_temperature_control_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            temperature_control_event = await self.remote.evt_temperatureControl.next(
                flush=False,
                timeout=STD_TIMEOUT,
            )
            self.assertTrue(temperature_control_event.heatingOn)
            self.assertFalse(temperature_control_event.coolingOn)

    async def test_ups_event(self):
        logging.info("test_ups_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            ups_event = await self.remote.evt_ups.next(flush=False, timeout=STD_TIMEOUT)
            self.assertTrue(ups_event.online)
            self.assertFalse(ups_event.batteryLow)
            self.assertFalse(ups_event.notOnMains)
            self.assertFalse(ups_event.communicationError)

    async def test_weather_event(self):
        logging.info("test_weather_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            weather_event = await self.remote.evt_weather.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(weather_event.weatherFlags, 0)

            self.weather_csc.windspeed = 1000
            weather_event = await self.remote.evt_weather.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(
                weather_event.weatherFlags, Weather.WeatherBad | Weather.WindBad
            )

            self.weather_csc.windspeed = 0
            self.weather_csc.humidity = 100
            weather_event = await self.remote.evt_weather.next(
                flush=False, timeout=STD_TIMEOUT
            )
            self.assertEqual(
                weather_event.weatherFlags, Weather.WeatherBad | Weather.HumidityBad
            )

    async def test_new_products(self):
        logging.info("test_new_products")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            for i in range(1, 5):
                large_file_event = await self.remote.evt_largeFileObjectAvailable.next(
                    flush=False,
                    timeout=STD_TIMEOUT,
                )
                url = large_file_event.url
                key = url[url.index("DREAM/") :]
                fileobj = await self.csc.s3bucket.download(key=key)
                file_contents = fileobj.getvalue().decode("utf-8")

                file_index = [
                    "DREAM_dream_2025-02-14T21:03:32.206_N_cloud_flat_000041_000073.txt",
                    "DREAM_dream_2025-02-14T21:03:32.207_W_cloud_science_000019_000056.txt",
                    "DREAM_dream_2025-02-14T21:03:32.207_S_calibration_000057_000047.txt",
                    "DREAM_dream_2025-02-14T21:03:32.207_B_image_bias_000017_000080.txt",
                ]
                for j, key_ending in enumerate(file_index):
                    if key.endswith(key_ending):
                        self.assertEqual(file_contents, f"This is data product {j+1}")
                        break

    async def test_data_upload_failure(self):
        """Test that the CSC enters FAULT state if the data upload fails."""
        logging.info("test_data_upload_failure")

        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_setLogLevel.set_start(level=40)
            self.remote.evt_logMessage.flush()

            with unittest.mock.patch.object(
                self.csc.s3bucket,
                "upload",
                side_effect=Exception("Simulated upload failure"),
            ), unittest.mock.patch(
                "builtins.open", unittest.mock.mock_open()
            ) as mock_file:
                mock_file.side_effect = IOError("Disk full")
                for _ in range(4):
                    log_message = await self.remote.evt_logMessage.next(
                        flush=False, timeout=STD_TIMEOUT
                    )
                    self.assertTrue("Simulated upload failure" in log_message.message)

                    log_message = await self.remote.evt_logMessage.next(
                        flush=False, timeout=STD_TIMEOUT
                    )
                    self.assertTrue("Upload data product failed" in log_message.message)

    async def test_data_download_failure(self):
        """Test that the CSC enters FAULT state if the data upload fails."""
        logging.info("test_data_upload_failure")

        await self.http_server.stop()

        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.remote.cmd_setLogLevel.set_start(level=40)

            for i in range(100):
                log_message = await self.remote.evt_logMessage.next(
                    flush=False, timeout=STD_TIMEOUT
                )
                self.log.debug(f"log message from CSC: {log_message.message}")
                if log_message.level == 40:
                    break
            else:
                self.assertTrue(False, "Failed to obtain an ERROR message")
            self.assertTrue(
                "Upload data product failed" in log_message.message,
                f"Unexpected log message: {log_message.message}",
            )

    async def test_use_precipitation(self):
        """Test for closure if use_precipitation=true in the config."""
        logging.info("test_use_precipitation")

        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            override="use_precipitation.yaml",
            simulation_mode=1,
        ):
            self.weather_csc.raining = True
            await asyncio.sleep(STD_TIMEOUT)  # Wait for event loop startup
            self.assertTrue(self.srv.weather is False)

    async def test_dont_use_precipitation(self):
        """Test for closure if use_precipitation=true in the config."""
        logging.info("test_dont_use_precipitation")

        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            self.weather_csc.raining = True
            await asyncio.sleep(STD_TIMEOUT)  # Wait for event loop startup
            self.assertTrue(self.srv.weather is True)
