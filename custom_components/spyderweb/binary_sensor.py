"""Binary sensors: per-output problem/ramping/alarms-enabled, and the safety relay."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Output
from .coordinator import SpyderWebConfigEntry, SpyderWebCoordinator
from .entity import SpyderWebEntity, SpyderWebOutputEntity

# The coordinator fetches the data, so entity updates need no limit.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OutputBinarySensorDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[Output], bool]
    attrs_fn: Callable[[Output], dict[str, Any]] | None = None


OUTPUT_BINARY_SENSORS: tuple[OutputBinarySensorDescription, ...] = (
    OutputBinarySensorDescription(
        key="problem",
        translation_key="output_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda o: o.has_error,
        attrs_fn=lambda o: {"error_code": o.error_code, "error_description": o.error_description},
    ),
    OutputBinarySensorDescription(
        key="ramping",
        translation_key="ramping",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda o: o.ramping_active,
        attrs_fn=lambda o: {"status": o.ramping},
    ),
    OutputBinarySensorDescription(
        key="alarms_enabled",
        translation_key="alarms_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda o: o.alarm_enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpyderWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [SafetyRelaySensor(coordinator)]
    entities.extend(
        OutputBinarySensor(coordinator, index, desc)
        for index in coordinator.data.outputs
        for desc in OUTPUT_BINARY_SENSORS
    )
    async_add_entities(entities)


class SafetyRelaySensor(SpyderWebEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "safety_relay_tripped"

    def __init__(self, coordinator: SpyderWebCoordinator) -> None:
        super().__init__(coordinator, key="safety_relay_tripped")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.system.safety_relay_tripped


class OutputBinarySensor(SpyderWebOutputEntity, BinarySensorEntity):
    entity_description: OutputBinarySensorDescription

    def __init__(
        self, coordinator: SpyderWebCoordinator, index: int, description: OutputBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, index, key=description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator.data.outputs[self._index])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data.outputs[self._index])
