# SPDX-FileCopyrightText: 2024-2025 Pascal Brogle @broglep
#
# SPDX-License-Identifier: MIT

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow
from homeassistant.loader import IntegrationNotFound, async_get_integration

from ..const import (  # noqa: TID252
    CONF_OPTION_TCP_PROXY,
    CONF_OPTION_TCP_PROXY_ENABLE,
    CONF_OPTION_TCP_PROXY_ENABLE_DEFAULT,
    CONF_OPTION_TCP_PROXY_PORT,
    CONF_OPTION_TCP_PROXY_PORT_DEFAULT,
    LOGGER,
)
from ..data import MeshtasticConfigEntry  # noqa: TID252
from .server import MeshtasticTcpProxy

_LOGGER = LOGGER.getChild(__name__)

_servers: dict[str, MeshtasticTcpProxy] = {}

# Integrations that can use the TCP proxy instead of their own connection to the
# radio. They get an integration discovery with host/port/name/node_id.
PROXY_CONSUMERS = ("meshtastic_ui",)
PROXY_HOST = "127.0.0.1"  # consumers run in the same Home Assistant instance


async def async_setup_tcp_proxy(
    hass: HomeAssistant,
    entry: MeshtasticConfigEntry,
) -> bool:
    tcp_proxy_config = entry.options.get(CONF_OPTION_TCP_PROXY, {})
    if tcp_proxy_config.get(CONF_OPTION_TCP_PROXY_ENABLE, CONF_OPTION_TCP_PROXY_ENABLE_DEFAULT) is False:
        return False

    tcp_proxy_port = tcp_proxy_config.get(CONF_OPTION_TCP_PROXY_PORT, CONF_OPTION_TCP_PROXY_PORT_DEFAULT)
    server = MeshtasticTcpProxy(entry.runtime_data.client._interface, port=tcp_proxy_port)  # noqa: SLF001
    try:
        await server.start()
    except Exception as e:  # noqa: BLE001
        _LOGGER.warning("Failed to start tcp proxy server: %s", e)
        return False
    _servers[entry.entry_id] = server

    try:
        await _async_announce_proxy(hass, entry, tcp_proxy_port)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Failed to announce tcp proxy", exc_info=True)
    return True


def _node_id(node: Mapping[str, Any] | None) -> str | None:
    if not node:
        return None
    user_id = (node.get("user") or {}).get("id")
    if isinstance(user_id, str) and user_id.startswith("!"):
        return user_id.lower()
    num = node.get("num")
    return f"!{num:08x}" if isinstance(num, int) else None


async def _async_announce_proxy(hass: HomeAssistant, entry: MeshtasticConfigEntry, port: int) -> None:
    """Let installed consumer integrations discover the proxy (shows up under Discovered)."""
    gateway_node = getattr(entry.runtime_data, "gateway_node", None)
    data = {
        "host": PROXY_HOST,
        "port": port,
        "name": entry.title,
        "node_id": _node_id(gateway_node),
        "meshtastic_entry_id": entry.entry_id,
    }
    for domain in PROXY_CONSUMERS:
        try:
            await async_get_integration(hass, domain)
        except IntegrationNotFound:
            continue
        _async_create_discovery(hass, domain, data)


@callback
def _async_create_discovery(hass: HomeAssistant, domain: str, data: dict[str, Any]) -> None:
    discovery_flow.async_create_flow(
        hass, domain, context={"source": SOURCE_INTEGRATION_DISCOVERY}, data=data
    )


async def async_unload_tcp_proxy(
    hass: HomeAssistant,  # noqa: ARG001
    entry: MeshtasticConfigEntry,
) -> bool:
    server = _servers.pop(entry.entry_id, None)
    if server:
        await server.stop()
        return True

    return False
