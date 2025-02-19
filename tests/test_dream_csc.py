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
import pathlib
import unittest

import lsst.ts.dream.csc as dream_csc
from lsst.ts import salobj
from lsst.ts.dream.csc.mock.dream_mock_http import MockDreamHTTPServer

STD_TIMEOUT = 2  # standard command timeout (sec)
TEST_CONFIG_DIR = pathlib.Path(__file__).parent / "config"


logging.basicConfig(
    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s", level=logging.DEBUG
)


class CscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.http_server = MockDreamHTTPServer(port=5001)
        await self.http_server.start()

        self.srv = dream_csc.mock.MockDream(
            host="0.0.0.0", port=0, log=logging.getLogger("foobar")
        )
        await self.srv.start_task
        self.mock_port = self.srv.port
        self.writer = None

    async def asyncTearDown(self):
        await self.srv.disconnect()
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        await self.srv.exit()
        await self.http_server.stop()

    def basic_make_csc(self, initial_state, config_dir, simulation_mode, **kwargs):
        return dream_csc.DreamCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
            mock_port=self.mock_port,
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

    async def test_dome_telemetry(self):
        logging.info("test_dome_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            dome_telemetry = await self.remote.tel_dome.next(flush=False)
            self.assertEqual(dome_telemetry.encoder, 110)

    async def test_environment_telemetry(self):
        logging.info("test_environment_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            environment_telemetry = await self.remote.tel_environment.next(flush=False)
            self.assertAlmostEqual(
                environment_telemetry.temperature[0], 25.9606, places=4
            )
            self.assertAlmostEqual(
                environment_telemetry.temperature[1], 25.8428, places=4
            )
            self.assertAlmostEqual(
                environment_telemetry.temperature[2], 25.1485, places=4
            )
            self.assertAlmostEqual(environment_telemetry.humidity[0], 50.3808, places=4)
            self.assertAlmostEqual(environment_telemetry.humidity[1], 50.3114, places=4)
            self.assertAlmostEqual(environment_telemetry.humidity[2], 50.3550, places=4)

    async def test_power_supply_telemetry(self):
        logging.info("test_power_supply_telemetry")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            power_supply_telemetry = await self.remote.tel_powerSupply.next(flush=False)
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
            ups_telemetry = await self.remote.tel_ups.next(flush=False)
            self.assertAlmostEqual(ups_telemetry.batteryCharge, 100.0)

    async def test_alerts_event(self):
        logging.info("test_alerts_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            alerts_event = await self.remote.evt_alerts.next(flush=False)
            self.assertFalse(alerts_event.outsideHumidity)
            self.assertFalse(alerts_event.outsideTemperature)

    async def test_errors_event(self):
        logging.info("test_errors_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            errors_event = await self.remote.evt_errors.next(flush=False)

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

    async def test_temperature_control_event(self):
        logging.info("test_temperature_control_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            temperature_control_event = await self.remote.evt_temperatureControl.next(
                flush=False
            )
            self.assertFalse(temperature_control_event.heatingOn)
            self.assertFalse(temperature_control_event.coolingOn)

    async def test_ups_event(self):
        logging.info("test_ups_event")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            ups_event = await self.remote.evt_ups.next(flush=False)
            self.assertTrue(ups_event.online)
            self.assertFalse(ups_event.batteryLow)
            self.assertFalse(ups_event.notOnMains)
            self.assertFalse(ups_event.communicationError)

    async def test_new_products(self):
        logging.info("test_new_products")
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            for i in range(1, 5):
                large_file_event = await self.remote.evt_largeFileObjectAvailable.next(
                    flush=False
                )
                url = large_file_event.url
                key = url[url.index("DREAM/") :]
                fileobj = await self.csc.s3bucket.download(key=key)
                file_contents = fileobj.getvalue().decode("utf-8")

                file_index = [
                    "N_cloud_flat_000041_000073.txt",
                    "W_cloud_science_000019_000056.txt",
                    "S_calibration_000057_000047.txt",
                    "B_image_bias_000017_000080.txt",
                ]
                for i, key_ending in enumerate(file_index):
                    if key.endswith(key_ending):
                        self.assertEqual(file_contents, f"This is data product {i+1}")
                        break

    async def test_data_upload_failure(self):
        """Test that the CSC enters FAULT state if the data upload fails."""
        logging.info("test_data_upload_failure")

        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            with unittest.mock.patch.object(
                self.csc.s3bucket,
                "upload",
                side_effect=Exception("Simulated upload failure"),
            ), unittest.mock.patch(
                "builtins.open", unittest.mock.mock_open()
            ) as mock_file:
                mock_file.side_effect = IOError("Disk full")
                await self.assert_next_summary_state(salobj.State.ENABLED)
                await self.assert_next_summary_state(salobj.State.FAULT)

    async def test_data_download_failure(self):
        """Test that the CSC enters FAULT state if the data upload fails."""
        logging.info("test_data_upload_failure")

        await self.http_server.stop()

        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=1,
        ):
            await self.assert_next_summary_state(salobj.State.ENABLED)
            await self.assert_next_summary_state(salobj.State.FAULT)
