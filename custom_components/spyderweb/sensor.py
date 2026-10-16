"""Sensors. Measurement sensors feed HA's recorder and long-term statistics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Output, System
from .const import CONF_TEMPERATURE_UNIT
from .coordinator import SpyderWebConfigEntry, SpyderWebCoordinator
from .entity import SpyderWebEntity, SpyderWebOutputEntity

# The coordinator fetches the data, so entity updates need no limit.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OutputSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Output], float | int | str | None]
    humidity_only: bool = False


@dataclass(frozen=True, kw_only=True)
class SystemSensorDescription(SensorEntityDescription):
    value_fn: Callable[[System], float | int | str | None]
    # Created only when the device reports the field (some fields depend on model/firmware).
    present_fn: Callable[[System], bool] = lambda _: True


def _temp(
    key: str,
    fn: Callable[[Output], float | None],
    *,
    diagnostic: bool = False,
    measurement: bool = True,
    enabled: bool = True,
) -> OutputSensorDescription:
    # Unit is set per entity from the config entry option (the device doesn't report it).
    return OutputSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT if measurement else None,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        entity_registry_enabled_default=enabled,
        suggested_display_precision=1,
        value_fn=fn,
    )


def _humidity(
    key: str, fn: Callable[[Output], float | None], *, diagnostic: bool = False
) -> OutputSensorDescription:
    return OutputSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=None if diagnostic else SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        entity_registry_enabled_default=not diagnostic,
        humidity_only=True,
        value_fn=fn,
    )


def _text(key: str, fn: Callable[[Output], str | None], *, enabled: bool = True) -> OutputSensorDescription:
    return OutputSensorDescription(
        key=key,
        translation_key=key,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        value_fn=fn,
    )


OUTPUT_SENSORS: tuple[OutputSensorDescription, ...] = (
    _temp("temperature", lambda o: o.temperature),
    _temp("setpoint", lambda o: o.setpoint),
    OutputSensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.power,
    ),
    _humidity("humidity", lambda o: o.humidity),
    # "Since last reset" extremes and thresholds: diagnostic, no statistics.
    _temp("temperature_max", lambda o: o.temperature_max, diagnostic=True, measurement=False),
    _temp("temperature_min", lambda o: o.temperature_min, diagnostic=True, measurement=False),
    _temp("high_alarm", lambda o: o.high_alarm, diagnostic=True, measurement=False),
    _temp("low_alarm", lambda o: o.low_alarm, diagnostic=True, measurement=False),
    _temp(
        "end_of_ramp_setpoint",
        lambda o: o.end_of_ramp_setpoint,
        diagnostic=True,
        measurement=False,
        enabled=False,  # only meaningful while a ramp is running
    ),
    _humidity("humidity_max", lambda o: o.humidity_max, diagnostic=True),
    _humidity("humidity_min", lambda o: o.humidity_min, diagnostic=True),
    OutputSensorDescription(
        key="power_limit",
        translation_key="power_limit",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda o: o.power_limit,
    ),
    _text("mode", lambda o: o.mode),
    # Same text as the problem binary sensor's attributes.
    _text("error", lambda o: o.error_description, enabled=False),
)

SYSTEM_SENSORS: tuple[SystemSensorDescription, ...] = (
    SystemSensorDescription(
        key="power_resets",
        translation_key="power_resets",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.power_resets,
    ),
    SystemSensorDescription(
        key="safety_relay",
        translation_key="safety_relay",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.safety_relay,
    ),
    SystemSensorDescription(
        key="internal_temperature",
        translation_key="internal_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda s: s.internal_temperature,
        present_fn=lambda s: s.internal_temperature is not None,
    ),
    SystemSensorDescription(
        key="internal_temperature_max",
        translation_key="internal_temperature_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda s: s.internal_temperature_max,
        present_fn=lambda s: s.internal_temperature_max is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpyderWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    unit = entry.options.get(CONF_TEMPERATURE_UNIT, UnitOfTemperature.FAHRENHEIT)
    system = coordinator.data.system
    entities: list[SensorEntity] = [
        SystemSensor(coordinator, desc, unit) for desc in SYSTEM_SENSORS if desc.present_fn(system)
    ]
    for output in coordinator.data.outputs.values():
        entities.extend(
            OutputSensor(coordinator, output.index, desc, unit)
            for desc in OUTPUT_SENSORS
            if not desc.humidity_only or output.has_humidity
        )
    async_add_entities(entities)


class OutputSensor(SpyderWebOutputEntity, SensorEntity):
    entity_description: OutputSensorDescription

    def __init__(
        self,
        coordinator: SpyderWebCoordinator,
        index: int,
        description: OutputSensorDescription,
        temperature_unit: str,
    ) -> None:
        super().__init__(coordinator, index, description.key)
        self.entity_description = description
        if description.device_class is SensorDeviceClass.TEMPERATURE:
            self._attr_native_unit_of_measurement = temperature_unit

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator.data.outputs[self._index])


class SystemSensor(SpyderWebEntity, SensorEntity):
    entity_description: SystemSensorDescription

    def __init__(
        self, coordinator: SpyderWebCoordinator, description: SystemSensorDescription, temperature_unit: str
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description
        if description.device_class is SensorDeviceClass.TEMPERATURE:
            self._attr_native_unit_of_measurement = temperature_unit

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator.data.system)
