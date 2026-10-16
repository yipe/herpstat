"""Problem binary sensors: per-output probe/device errors and the safety relay."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpyderWebConfigEntry, SpyderWebCoordinator
from .entity import SpyderWebEntity, SpyderWebOutputEntity

# The coordinator fetches the data, so entity updates need no limit.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpyderWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [SafetyRelaySensor(coordinator)]
    entities.extend(OutputProblemSensor(coordinator, index) for index in coordinator.data.outputs)
    async_add_entities(entities)


class SafetyRelaySensor(SpyderWebEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "safety_relay_tripped"

    def __init__(self, coordinator: SpyderWebCoordinator) -> None:
        super().__init__(coordinator, key="safety_relay_tripped")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.system.safety_relay_tripped


class OutputProblemSensor(SpyderWebOutputEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "output_problem"

    def __init__(self, coordinator: SpyderWebCoordinator, index: int) -> None:
        super().__init__(coordinator, index, key="problem")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.outputs[self._index].has_error

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        output = self.coordinator.data.outputs[self._index]
        return {"error_code": output.error_code, "error_description": output.error_description}
