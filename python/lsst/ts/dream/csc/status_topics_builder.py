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

import logging
import math
from datetime import datetime
from enum import Enum
from functools import partial
from typing import Any, TypeVar

from astropy.time import Time
from lsst.ts.xml.enums import DREAM

TopicData = dict[str, str | bool | int | float | list[bool] | list[float]]
SampleList = list[tuple[str, TopicData]]

# A map connecting each camera's name in the DREAM status message to
# that camera's identity in the ts-xml DREAM.Camera enum.
cameras = {
    "E": DREAM.Camera.East,
    "W": DREAM.Camera.West,
    "N": DREAM.Camera.North,
    "C": DREAM.Camera.Central,
    "S": DREAM.Camera.South,
}

# The warning string for each of the warnings that are represented
# in the DREAM.Warning enum.
warnings = {
    "Power saving mode activated": DREAM.Warning.PowersavingActivated,
    "UPS is on battery": DREAM.Warning.UpsOnBattery,
    "Dome opening blocked by NO-GO": DREAM.Warning.DomeClosedByNogo,
    "Dome opening blocked by sun alt": DREAM.Warning.DomeClosedBySun,
    "Dome opening blocked by temp/hum": DREAM.Warning.DomeClosedByEnv,
    "Dome opening blocked by UPS error": DREAM.Warning.DomeClosedByUps,
    "Dome opening blocked by timer": DREAM.Warning.DomeClosedByTimer,
    "User stopped dome movement": DREAM.Warning.DomeStopped,
    "User forced dome open": DREAM.Warning.DomeForcedOped,
    "Dome opening blocked by backdoor": DREAM.Warning.DomeClosedByDoor,
    "Rubin client not connected": DREAM.Warning.RubinNoClient,
    "More than 1 client on rubin socket": DREAM.Warning.RubinMultipleClients,
    "Rubin client update too old": DREAM.Warning.RubinClientStale,
    "Rubin-provided weather flag too old": DREAM.Warning.RubinWeatherTooOld,
    "Bad weather flag set by Rubin": DREAM.Warning.RubinBadWeather,
    "NO-GO for dome open set by Rubin": DREAM.Warning.RubinNogo,
    "There is an active script client": DREAM.Warning.ScriptClientActive,
    "Dream inlet humidity high": DREAM.Warning.InletHumWarning,
    "Dream inlet temperature low": DREAM.Warning.InletTempWarning,
    "North camera not connected": DREAM.Warning.CameraNNotConnected,
    "South camera not connected": DREAM.Warning.CameraSNotConnected,
    "East camera not connected": DREAM.Warning.CameraENotConnected,
    "West camera not connected": DREAM.Warning.CameraWNotConnected,
    "Center camera not connected": DREAM.Warning.CameraCNotConnected,
    "Dome movements are simulated": DREAM.Warning.SimulatedDome,
    "LEDs are simulated": DREAM.Warning.SimulatedLeds,
    "UPS is simulated": DREAM.Warning.SimulatedUps,
    "PDU is simulated": DREAM.Warning.SimulatedPdu,
    "Temp/humidity sensors are simulated": DREAM.Warning.SimulatedEnv,
    "Sun angle is simulated": DREAM.Warning.SimulatedSun,
}

# The error string for each of the errors that are represented
# in the DREAM.Error enum.
errors = {
    "Both open and closed are pushed": DREAM.Error.LimitSwitchError,
    "Dome should be closed but it is not": DREAM.Error.DomeError,
    "Backdoor is open": DREAM.Error.BackdoorOpen,
    "Door is open": DREAM.Error.DoorOpen,
    "UPS not reachable or not responding": DREAM.Error.UpsError,
    "PDU 1 not reachable": DREAM.Error.Pdu1Error,
    "PDU 2 not reachable": DREAM.Error.Pdu2Error,
    "Temp hum sensor not reachable": DREAM.Error.TemphumError,
    "PSU reports a problem": DREAM.Error.PsuError,
    "UPS battery needs replacing": DREAM.Error.UpsBatteryNeedsReplace,
    "Camera bay temperature too high": DREAM.Error.CameraBayTempError,
    "Humidity in camera bay too high": DREAM.Error.CameraBayHumError,
    "Humidity in electronics box > limit": DREAM.Error.ElectronicsHumidityError,
    "Humidty under dome > limit": DREAM.Error.DomeHumidityError,
}

# The keys in the PDU status dictionary in the order prescribed by
# the DREAM ts-xml interface.
pdu_status = (
    "Switch",
    "USB hub",
    "PSU 1",
    "PSU 2",
    "Central Camera",
    "North Camera",
    "East Camera",
    "South Camera",
    "West Camera",
    "Command Server",
    "Central Server",
    "North Server",
    "East Server",
    "South Server",
    "West Server",
)

# For the relays in the DREAM system, this dictionary provides
# the key name for each relay in the DREAM status message, and
# the value used when that relay is switched.
relays = {
    "motor_relay": "on",
    "motor_dir": "closing",
    "peltier_relay": "on",
    "peltier_dir": "cooling",
    "window_heaters": "on",
}

# The keys used in the `temp_hum` DREAM status structure, in the order
# expected by the DREAM XML interface.
environment = (
    "electronics_top",
    "camera_bay",
    "electronics_box",
    "rack_top",
    "rack_bottom",
    "dream_inlet",
)


def enum_value_from_str(enum_cls: type[Enum], s: str | None) -> int:
    """Convert a string to the corresponding enum value, or -1 if invalid.

    The input string is capitalized before lookup to match the convention
    of ts-xml. Returns -1 if the string is None or does not match any member
    of the enum.

    Parameters
    ----------
    enum_cls : `type[Enum]`
        The enumeration class to look up values in.
    s : `str` | `None`
        The string name of the enum member

    Returns
    -------
    int
        The corresponding enum value, or -1 if the input is None or invalid.
    """
    if s is None:
        return -1
    try:
        return enum_cls[s.capitalize()].value
    except KeyError:
        return -1


camera_server_mode = partial(enum_value_from_str, DREAM.CameraServerMode)
dome_state = partial(enum_value_from_str, DREAM.DomeState)
target_dome_state = partial(enum_value_from_str, DREAM.DomeTargetState)
heater_state = partial(enum_value_from_str, DREAM.HeaterState)
peltier_state = partial(enum_value_from_str, DREAM.PeltierState)


def isot_to_tai_unix(isot_str: str | None) -> float:
    """Convert an ISO-8601 string (with or without timezone offset).

    Take an ISOT formatted timestamp and convert it to TAI seconds since the
    Unix epoch (1970-01-01T00:00:00 TAI).

    Parameters
    ----------
    isot_str : str
        ISO-8601 timestamp, e.g. '2025-09-22T09:57:16.193+00:00',
        the format used by DREAM.

    Returns
    -------
    float
        Seconds since TAI epoch aligned with 1970-01-01T00:00:00 TAI,
        the format used by Rubin, or NaN, if `isot_str` is None.
    """
    if isot_str is None:
        return math.nan

    # datetime can handle the timezone sent by DREAM.
    dt = datetime.fromisoformat(isot_str)
    return float(Time(dt).unix_tai)


T = TypeVar("T", int, float)


def to_value(value: T | None, default: T) -> T:
    """
    Return the given value, or a default if None.

    For parameters that may be None but need to be forced
    to a specific type for Kafka.

    Parameters
    ----------
    value : `int` | `float` | `None`
        The input value.
    default : `int` | `float`
        The fallback value to use if `value` is `None`.

    Returns
    -------
    int | float
        The same value, or the default if the input is None.
    """
    return default if value is None else value


def to_int(value: int | None) -> int:
    """Return the integer value or -1 if None."""
    return to_value(value, -1)


def to_float(value: float | None) -> float:
    """Return the float value or NaN if None."""
    return to_value(value, math.nan)


def map_to_bitfield(
    messages: list[str], message_map: dict[str, DREAM.Camera]
) -> tuple[int, str]:
    """Aggregate the list of messages into a bitmap.

    The dictionary is used to map the error or warning strings into bitmap
    values. These values are collected together, and any string values
    not present in the map are reported in a "leftover" semicolon-separated
    string.

    Parameters
    ----------
    messages : `list[str]`
        Error/warning message strings.

    Returns
    -------
    tuple[int, str]
        (bitmask of recognized errors/warnings, semicolon-separated unknowns).
    """
    bitmask = 0
    unknowns: list[str] = []

    for msg in messages:
        if msg in message_map:
            bitmask |= message_map[msg].value
        else:
            unknowns.append(msg)

    return bitmask, ";".join(unknowns)


class StatusTopicsBuilder:
    """
    Construct SAL topic dictionaries from DREAM status messages.

    This class translates the nested `dream_status` dictionary provided by
    DREAM into the topic data structures expected by the XML interface.
    Each method extracts and converts a specific portion of the status into
    a dictionary keyed by the corresponding SAL topic name, which can
    then be used by the topic's `set_write` method.

    Parameters
    ----------
    log : `logging.Logger`
        A logger to be used.
    battery_low_threshold : `float`
        Fractional battery charge below which the UPS is considered low.
    """

    def __init__(self, *, log: logging.Logger, battery_low_threshold: float):
        self.log = log
        self.battery_low_threshold = battery_low_threshold
        self.camera_event_cache: dict[DREAM.Camera, TopicData] = dict()

    def get_events_camera(self, dream_status: dict[str, Any]) -> SampleList:
        """Build `camera` event topics.

        Extract per-camera information (e.g., image counts, last image
        metadata, pixel statistics) and package into `evt_camera_*` topics.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            List of `camera` events to be published.
        """
        camera_events: SampleList = []

        cameras_dict = dream_status["cameras"]
        for camera_id, camera in cameras_dict.items():
            source = cameras[camera_id]
            new_event: TopicData = dict()

            new_event["source"] = source
            new_event["cameraMode"] = camera_server_mode(camera["camera_mode"])
            new_event["nBlank"] = to_int(camera["num_blanks"])
            new_event["nDark"] = to_int(camera["num_darks"])
            new_event["nBias"] = to_int(camera["num_bias"])
            new_event["nFlat"] = to_int(camera["num_flats"])
            new_event["nScience"] = to_int(camera["num_science"])
            new_event["nMissed"] = to_int(camera["num_missed"])
            new_event["lastSequenceNumber"] = to_int(camera["last_image_seq"])
            new_event["lastTriggerTime"] = isot_to_tai_unix(
                camera["last_image_triggertime"]
            )
            new_event["lastImageTimingLatency"] = to_float(
                camera["last_image_timing_latency"]
            )
            new_event["lastImageUSBLatency"] = to_float(
                camera["last_image_usb_latency"]
            )
            new_event["lastImageArtificialLatency"] = to_float(
                camera["last_image_artificial_latency"]
            )
            new_event["lastImageType"] = camera_server_mode(camera["last_image_type"])
            new_event["lastImagePixelMedian"] = to_float(
                camera["last_image_pixel_median"]
            )

            if (
                source not in self.camera_event_cache
                or self.camera_event_cache[source] != new_event
            ):
                # Include the new event for publication only if it has changed.
                # Normally SalObj will take care of this for us, but the
                # functionality does not work if an event is being multiplexed,
                # as in this case where the same event is used for five
                # different cameras.
                camera_events.append(("evt_camera", new_event))

            self.camera_event_cache[source] = new_event

        return camera_events

    def get_event_errors(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `evt_errors` topic.

        Map DREAM error strings into high-level error flags expected by SAL.
        Replicate temperature sensor communication flags for compatibility.
        It might make sense later to phase out this event in favor of
        `errorFlags` and `additionalErrors` in the `status` event.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `errors` event to be published.
        """
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

        error_dict: TopicData = {
            flag: any(
                error_string in dream_status["errors"]
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
        return [("evt_errors", error_dict)]

    def get_event_power_supply(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `evt_powerSupply` topic.

        Infer power-supply temperature and input-voltage errors from the
        structured `psu_status` block.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `powerSupply` event to be published.
        """
        power_supply_event: TopicData = {
            "temperatureError": dream_status["psu_status"]["temp_error"],
            "inputVoltageError": dream_status["psu_status"]["input_error"],
        }
        return [("evt_powerSupply", power_supply_event)]

    def get_event_status(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `evt_status` topic.

        Combine observing mode, dome/heater/peltier states, relay states,
        PDU power status, and aggregated error/warning bitfields.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `status` event to be published.
        """
        status_event: TopicData = dict()

        status_event["observingMode"] = camera_server_mode(
            dream_status["actual_observing_mode"]
        )
        status_event["targetObservingMode"] = camera_server_mode(
            dream_status["target_observing_mode"]
        )
        status_event["dome"] = dome_state(dream_status["actual_dome_state"])
        status_event["targetDome"] = target_dome_state(
            dream_status["target_dome_state"]
        )
        status_event["heater"] = heater_state(dream_status["actual_heater_state"])
        status_event["targetHeater"] = heater_state(dream_status["target_heater_state"])
        status_event["peltier"] = peltier_state(dream_status["actual_peltier_state"])
        status_event["targetPeltier"] = peltier_state(
            dream_status["target_peltier_state"]
        )
        status_event["power"] = [
            dream_status["pdu_status"][index] for index in pdu_status
        ]
        status_event["relayState"] = [
            dream_status["electronics"][k] == v for k, v in relays.items()
        ]

        error_flags, error_extras = map_to_bitfield(dream_status["errors"], errors)
        warning_flags, warning_extras = map_to_bitfield(
            dream_status["warnings"], warnings
        )

        status_event["errorFlags"] = error_flags
        status_event["warningFlags"] = warning_flags
        status_event["additionalErrors"] = error_extras
        status_event["additionalWarnings"] = warning_extras

        return [("evt_status", status_event)]

    def get_event_temperature_control(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `evt_temperatureControl` topic.

        Encode whether peltier-based heating or cooling is currently active.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `temperatureControl` event to be published.
        """
        peltier_relay = dream_status["electronics"]["peltier_relay"] == "on"
        peltier_direction = dream_status["electronics"]["peltier_dir"]
        heating_on = peltier_relay and (peltier_direction == "heating")
        cooling_on = peltier_relay and (peltier_direction == "cooling")

        temperature_control_event = {
            "heatingOn": heating_on,
            "coolingOn": cooling_on,
        }

        return [("evt_temperatureControl", temperature_control_event)]

    def get_event_ups(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `evt_ups` topic.

        Report UPS health and communication state, including online/offline,
        battery level, mains power status, and communication errors.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `ups` event to be published.
        """
        ups_online = dream_status["ups_status"]["ups_status"] == "ONLINE"
        ups_battery_low = (
            dream_status["ups_status"]["battery_charge"] < self.battery_low_threshold
        )
        ups_not_on_mains = "UPS is on battery" in dream_status["warnings"]
        ups_communication_error = (
            "UPS not reachable or not responding" in dream_status["errors"]
        )

        ups_event = {
            "online": ups_online,
            "batteryLow": ups_battery_low,
            "notOnMains": ups_not_on_mains,
            "communicationError": ups_communication_error,
        }

        return [("evt_ups", ups_event)]

    def get_telemetry_camera(self, dream_status: dict[str, Any]) -> SampleList:
        """Build `camera` telemetry topics.

        Include heartbeat timestamps and CCD temperature readings for each
        camera.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of `camera` telemetry samples to be published.
        """
        camera_telemetry: TopicData = dict()

        last_heartbeat = [math.nan] * len(cameras)
        temperature = [math.nan] * len(cameras)

        cameras_dict = dream_status["cameras"]
        for camera_id, camera in cameras_dict.items():
            index = cameras[camera_id].value
            last_heartbeat[index] = isot_to_tai_unix(camera["last_heartbeat"])
            temperature[index] = to_float(camera["ccd_temp"])

        camera_telemetry["lastCameraHeartbeatTimestamp"] = last_heartbeat
        camera_telemetry["ccdTemperature"] = temperature

        return [("tel_camera", camera_telemetry)]

    def get_telemetry_dome(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `tel_dome` topic.

        Report dome encoder position.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `dome` telemetry sample to be published.
        """
        dome_telemetry: TopicData = dict()
        dome_telemetry["encoder"] = dream_status["dome_position"]
        return [("tel_dome", dome_telemetry)]

    def get_telemetry_environment(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `tel_environment` topic.

        Package environmental telemetry (temperature and humidity) for each
        monitored location into ordered arrays.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `environment` telemetry sample to be published.
        """
        environment_telemetry: TopicData = dict()

        environment_telemetry["temperature"] = [
            dream_status["temp_hum"][index]["temperature"] for index in environment
        ]
        environment_telemetry["humidity"] = [
            dream_status["temp_hum"][index]["humidity"] for index in environment
        ]

        return [("tel_environment", environment_telemetry)]

    def get_telemetry_power_supply(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `tel_powerSupply` topic.

        Report voltage and current telemetry (feedback and setpoint).

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `powerSupply` telemetry sample to be published.
        """
        power_supply_telemetry: TopicData = dict()

        power_supply_telemetry["voltage"] = [
            dream_status["psu_status"]["voltage_feedback"],
            dream_status["psu_status"]["voltage_setpoint"],
        ]
        power_supply_telemetry["current"] = [
            dream_status["psu_status"]["current_feedback"],
            dream_status["psu_status"]["current_setpoint"],
        ]

        return [("tel_powerSupply", power_supply_telemetry)]

    def get_telemetry_ups(self, dream_status: dict[str, Any]) -> SampleList:
        """Build the `tel_ups` topic.

        Report UPS telemetry including charge, temperature, voltage, time
        remaining, output load, and output current.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        SampleList
            A list of (one) `ups` telemetry sample to be published.
        """
        ups_telemetry: TopicData = dict()

        ups_telemetry["batteryCharge"] = dream_status["ups_status"]["battery_charge"]
        ups_telemetry["batteryTemperature"] = dream_status["ups_status"][
            "battery_temperature"
        ]
        ups_telemetry["batteryVoltage"] = dream_status["ups_status"]["battery_voltage"]
        ups_telemetry["timeRemaining"] = dream_status["ups_status"]["battery_remaining"]
        ups_telemetry["outputLoad"] = dream_status["ups_status"]["output_load"]
        ups_telemetry["outputCurrent"] = dream_status["ups_status"]["output_current"]
        if "last_online" in dream_status["ups_status"]:
            ups_telemetry["lastOnline"] = float(
                Time(
                    dream_status["ups_status"]["last_online"],
                    scale="utc",
                    format="unix",
                ).unix_tai
            )

        return [("tel_ups", ups_telemetry)]

    def __call__(self, dream_status: dict[str, Any]) -> SampleList:
        """Build all event and telemetry topics from a DREAM status message.

        Invokes each builder method in sequence, merging results into a single
        dictionary. If an unexpected format is encountered, logs an exception
        and skips that section.

        Parameters
        ----------
        dream_status : dict[str, Any]
            The raw status dictionary provided by DREAM, containing camera,
            dome, UPS, environmental, and error/warning information.

        Returns
        -------
        dict[str, TopicData]
            Dictionary mapping all topic names to their payloads.
        """
        builder_functions = {
            "evt_camera": self.get_events_camera,
            "evt_errors": self.get_event_errors,
            "evt_status": self.get_event_status,
            "evt_powerSupply": self.get_event_power_supply,
            "evt_temperatureControl": self.get_event_temperature_control,
            "evt_ups": self.get_event_ups,
            "tel_camera": self.get_telemetry_camera,
            "tel_dome": self.get_telemetry_dome,
            "tel_environment": self.get_telemetry_environment,
            "tel_powerSupply": self.get_telemetry_power_supply,
            "tel_ups": self.get_telemetry_ups,
        }

        all_topics: SampleList = []
        for telemetry_name, builder_function in builder_functions.items():
            try:
                all_topics += builder_function(dream_status)
            except KeyError:
                self.log.exception(
                    "While reading {telemetry_name}: Events status from DREAM had unexpected format!"
                )

        return all_topics
