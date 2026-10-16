"""Base entity: one HA device per Herpstat unit."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SpyderWebCoordinator


class SpyderWebEntity(CoordinatorEntity[SpyderWebCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SpyderWebCoordinator, key: str) -> None:
        super().__init__(coordinator)
        system = coordinator.data.system
        mac = format_mac(system.mac)
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer="Spyder Robotics",
            model=f"Herpstat {len(coordinator.data.outputs)} SpyderWeb",
            name=system.nickname or "Herpstat",
            sw_version=system.firmware,
            configuration_url=f"http://{coordinator.host}/",
        )


class SpyderWebOutputEntity(SpyderWebEntity):
    """Entity for one output; its name is prefixed with the output's nickname, e.g. "Lamp temperature"."""

    def __init__(self, coordinator: SpyderWebCoordinator, index: int, key: str) -> None:
        super().__init__(coordinator, key=f"output{index}_{key}")
        self._index = index
        self._attr_translation_placeholders = {"output": coordinator.data.outputs[index].nickname}

    @property
    def available(self) -> bool:
        return super().available and self._index in self.coordinator.data.outputs
