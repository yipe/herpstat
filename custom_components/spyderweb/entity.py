"""Base entity: one HA device per Herpstat unit."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SpyderWebCoordinator


class SpyderWebEntity(CoordinatorEntity[SpyderWebCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SpyderWebCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        system = coordinator.data.system
        mac = format_mac(system.mac)
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer="Spyder Robotics",
            model=f"Herpstat {len(coordinator.data.outputs)} SpyderWeb",
            name=system.nickname or "Herpstat",
            sw_version=system.firmware,
            configuration_url=f"http://{coordinator.host}/",
        )
