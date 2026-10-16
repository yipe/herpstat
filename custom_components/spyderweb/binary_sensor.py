"""Problem binary sensors: per-output probe/device errors and the safety relay."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SpyderWebConfigEntry, SpyderWebCoordinator
from .entity import SpyderWebEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpyderWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [SafetyRelaySensor(coordinator)]
    entities.extend(
        OutputProblemSensor(coordinator, output.index, output.nickname)
        for output in coordinator.data.outputs.values()
    )
    async_add_entities(entities)


class SafetyRelaySensor(SpyderWebEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SpyderWebCoordinator) -> None:
        super().__init__(coordinator, key="safety_relay_tripped", name="Safety relay tripped")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.system.safety_relay_tripped


class OutputProblemSensor(SpyderWebEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SpyderWebCoordinator, index: int, nickname: str) -> None:
        super().__init__(coordinator, key=f"output{index}_problem", name=f"{nickname} problem")
        self._index = index

    @property
    def available(self) -> bool:
        return super().available and self._index in self.coordinator.data.outputs

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.outputs[self._index].has_error

    @property
    def extra_state_attributes(self) -> dict[str, int | str | None]:
        output = self.coordinator.data.outputs[self._index]
        return {"error_code": output.error_code, "error_description": output.error_description}
