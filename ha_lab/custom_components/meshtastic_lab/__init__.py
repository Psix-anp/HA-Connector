"""Test-only driver for Meshtastic Extended end-to-end Home Assistant checks."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from custom_components.meshtastic.api import (
    ATTR_EVENT_MESHTASTIC_API_CONFIG_ENTRY_ID,
    ATTR_EVENT_MESHTASTIC_API_DATA,
    EVENT_MESHTASTIC_API_TEXT_MESSAGE,
)
from custom_components.meshtastic.const import DOMAIN as MESHTASTIC_DOMAIN
from custom_components.meshtastic.logbook import async_setup_message_logger

DOMAIN = "meshtastic_lab"
SERVICE_INJECT_MESSAGE = "inject_message"
LAB_ENTRY_ID = "ha-lab-entry"
LAB_GATEWAY = 0x11111111
LAB_REMOTE = 0x22222222


class _FakeClient:
    def get_node_info(self, node_id: int) -> Any:
        if node_id == LAB_REMOTE:
            return SimpleNamespace(long_name="HA Lab Remote", user_id="!22222222")
        if node_id == LAB_GATEWAY:
            return SimpleNamespace(long_name="HA Lab Gateway", user_id="!11111111")
        return None


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the test driver inside a real Home Assistant instance."""
    entity_registry = er.async_get(hass)
    dm_entry = entity_registry.async_get_or_create(
        MESHTASTIC_DOMAIN,
        MESHTASTIC_DOMAIN,
        "ha_lab_direct_messages",
        suggested_object_id="ha_lab_direct_messages",
    )
    channel_entry = entity_registry.async_get_or_create(
        MESHTASTIC_DOMAIN,
        MESHTASTIC_DOMAIN,
        "ha_lab_channel_primary",
        suggested_object_id="ha_lab_channel_primary",
    )
    hass.states.async_set(dm_entry.entity_id, "logging", {"friendly_name": "Direct Messages"})
    hass.states.async_set(channel_entry.entity_id, "logging", {"friendly_name": "Channel Primary"})

    fake_entry = SimpleNamespace(
        entry_id=LAB_ENTRY_ID,
        runtime_data=SimpleNamespace(client=_FakeClient()),
    )
    remove_logger = await async_setup_message_logger(
        hass,
        fake_entry,
        message_entities={
            "direct": dm_entry.entity_id,
            "channels": {0: channel_entry.entity_id},
        },
    )

    async def _inject_message(call: ServiceCall) -> None:
        target = call.data["target"]
        marker = call.data["message"]
        to = {"node": LAB_GATEWAY} if target == "dm" else {"channel": 0}
        hass.bus.async_fire(
            EVENT_MESHTASTIC_API_TEXT_MESSAGE,
            {
                ATTR_EVENT_MESHTASTIC_API_CONFIG_ENTRY_ID: LAB_ENTRY_ID,
                ATTR_EVENT_MESHTASTIC_API_DATA: {
                    "from": LAB_REMOTE,
                    "gateway": LAB_GATEWAY,
                    "to": to,
                    "message": marker,
                    "pki_encrypted": target == "dm",
                    "want_ack": True,
                    "acknowledged": True,
                    "status": "acked",
                },
            },
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_INJECT_MESSAGE,
        _inject_message,
        schema=vol.Schema(
            {
                vol.Required("target"): vol.In(["dm", "channel"]),
                vol.Required("message"): str,
            }
        ),
    )

    async def _shutdown(_event: Any) -> None:
        remove_logger()

    hass.bus.async_listen_once("homeassistant_stop", _shutdown)
    hass.data[DOMAIN] = {
        "dm_entity_id": dm_entry.entity_id,
        "channel_entity_id": channel_entry.entity_id,
    }
    return True
