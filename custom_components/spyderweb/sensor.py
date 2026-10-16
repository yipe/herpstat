"""Sensors. Measurement sensors feed HA's recorder and long-term statistics (the history store)."""

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
from .entity import SpyderWebEntity


@dataclass(frozen=True, kw_only=True)
class OutputSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Output], float | int | str | None]
    humidity_only: bool = False


@dataclass(frozen=True, kw_only=True)
class SystemSensorDescription(SensorEntityDescription):
    value_fn: Callable[[System], float | int | str | None]


def _temp(
    key: str,
    name: str,
    fn: Callable[[Output], float | None],
    *,
    diagnostic: bool = False,
    measurement: bool = True,
) -> OutputSensorDescription:
    # Unit is set per entity from the config entry option (the device doesn't report it).
    return OutputSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT if measurement else None,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        suggested_display_precision=1,
        value_fn=fn,
    )


def _humidity(
    key: str, name: str, fn: Callable[[Output], float | None], *, diagnostic: bool = False
) -> OutputSensorDescription:
    return OutputSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=None if diagnostic else SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        humidity_only=True,
        value_fn=fn,
    )


def _text(key: str, name: str, icon: str, fn: Callable[[Output], str | None]) -> OutputSensorDescription:
    return OutputSensorDescription(
        key=key, name=name, icon=icon, entity_category=EntityCategory.DIAGNOSTIC, value_fn=fn
    )


OUTPUT_SENSORS: tuple[OutputSensorDescription, ...] = (
    _temp("temperature", "temperature", lambda o: o.temperature),
    _temp("setpoint", "setpoint", lambda o: o.setpoint),
    OutputSensorDescription(
        key="power",
        name="power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash",
        value_fn=lambda o: o.power,
    ),
    _humidity("humidity", "humidity", lambda o: o.humidity),
    # "Since last reset" extremes and thresholds: diagnostic, no statistics.
    _temp(
        "temperature_max", "temperature max", lambda o: o.temperature_max, diagnostic=True, measurement=False
    ),
    _temp(
        "temperature_min", "temperature min", lambda o: o.temperature_min, diagnostic=True, measurement=False
    ),
    _temp("high_alarm", "high alarm", lambda o: o.high_alarm, diagnostic=True, measurement=False),
    _temp("low_alarm", "low alarm", lambda o: o.low_alarm, diagnostic=True, measurement=False),
    _temp(
        "end_of_ramp_setpoint",
        "end of ramp setpoint",
        lambda o: o.end_of_ramp_setpoint,
        diagnostic=True,
        measurement=False,
    ),
    _humidity("humidity_max", "humidity max", lambda o: o.humidity_max, diagnostic=True),
    _humidity("humidity_min", "humidity min", lambda o: o.humidity_min, diagnostic=True),
    OutputSensorDescription(
        key="power_limit",
        name="power limit",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:flash-outline",
        value_fn=lambda o: o.power_limit,
    ),
    _text("mode", "mode", "mdi:cog-outline", lambda o: o.mode),
    _text("ramping", "ramping", "mdi:chart-timeline-variant", lambda o: o.ramping),
    _text("error", "error", "mdi:alert-circle-outline", lambda o: o.error_description),
)

SYSTEM_SENSORS: tuple[SystemSensorDescription, ...] = (
    SystemSensorDescription(
        key="power_resets",
        name="Power resets",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:restart",
        value_fn=lambda s: s.power_resets,
    ),
    SystemSensorDescription(
        key="safety_relay",
        name="Safety relay",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:electric-switch",
        value_fn=lambda s: s.safety_relay,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpyderWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    unit = entry.options.get(CONF_TEMPERATURE_UNIT, UnitOfTemperature.FAHRENHEIT)
    entities: list[SensorEntity] = [SystemSensor(coordinator, desc) for desc in SYSTEM_SENSORS]
    for output in coordinator.data.outputs.values():
        entities.extend(
            OutputSensor(coordinator, output, desc, unit)
            for desc in OUTPUT_SENSORS
            if not desc.humidity_only or output.has_humidity
        )
    async_add_entities(entities)


class OutputSensor(SpyderWebEntity, SensorEntity):
    entity_description: OutputSensorDescription

    def __init__(
        self,
        coordinator: SpyderWebCoordinator,
        output: Output,
        description: OutputSensorDescription,
        temperature_unit: str,
    ) -> None:
        super().__init__(
            coordinator,
            key=f"output{output.index}_{description.key}",
            name=f"{output.nickname} {description.name}",
        )
        self._index = output.index
        if description.device_class is SensorDeviceClass.TEMPERATURE:
            self._attr_native_unit_of_measurement = temperature_unit
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self._index in self.coordinator.data.outputs

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator.data.outputs[self._index])


class SystemSensor(SpyderWebEntity, SensorEntity):
    entity_description: SystemSensorDescription

    def __init__(self, coordinator: SpyderWebCoordinator, description: SystemSensorDescription) -> None:
        super().__init__(coordinator, key=description.key, name=description.name)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.value_fn(self.coordinator.data.system)
