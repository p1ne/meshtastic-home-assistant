# SPDX-FileCopyrightText: 2026 p1ne
#
# SPDX-License-Identifier: MIT

"""The TCP proxy announces itself to consumer integrations (Meshtastic UI) through integration discovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import HomeAssistant
from homeassistant.loader import IntegrationNotFound
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshtastic import meshtastic_tcp
from custom_components.meshtastic.const import DOMAIN

GATEWAY = {"num": 0x2A92AE57, "user": {"id": "!2a92ae57", "longName": "MiFi 3860"}}


def _entry(hass: HomeAssistant, *, port: int = 4403) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MiFi3860",
        data={"connection_type": "tcp", "tcp_host": "192.168.1.66"},
        options={"tcp_proxy": {"enable": True, "port": port}},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(gateway_node=GATEWAY, client=SimpleNamespace(_interface=MagicMock()))
    return entry


async def test_proxy_start_announces_to_meshtastic_ui(hass: HomeAssistant) -> None:
    entry = _entry(hass, port=4404)
    with (
        patch.object(meshtastic_tcp, "MeshtasticTcpProxy") as proxy,
        patch.object(meshtastic_tcp, "async_get_integration", AsyncMock()) as get_integration,
        patch.object(meshtastic_tcp.discovery_flow, "async_create_flow") as create_flow,
    ):
        proxy.return_value.start = AsyncMock()
        assert await meshtastic_tcp.async_setup_tcp_proxy(hass, entry)

    get_integration.assert_awaited_once_with(hass, "meshtastic_ui")
    create_flow.assert_called_once_with(
        hass,
        "meshtastic_ui",
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={
            "host": "127.0.0.1",
            "port": 4404,
            "name": "MiFi3860",
            "node_id": "!2a92ae57",
            "meshtastic_entry_id": entry.entry_id,
        },
    )


async def test_no_announcement_without_consumer(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch.object(meshtastic_tcp, "MeshtasticTcpProxy") as proxy,
        patch.object(meshtastic_tcp, "async_get_integration", AsyncMock(side_effect=IntegrationNotFound("x"))),
        patch.object(meshtastic_tcp.discovery_flow, "async_create_flow") as create_flow,
    ):
        proxy.return_value.start = AsyncMock()
        assert await meshtastic_tcp.async_setup_tcp_proxy(hass, entry)
    create_flow.assert_not_called()


async def test_no_announcement_when_proxy_fails_to_start(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch.object(meshtastic_tcp, "MeshtasticTcpProxy") as proxy,
        patch.object(meshtastic_tcp.discovery_flow, "async_create_flow") as create_flow,
    ):
        proxy.return_value.start = AsyncMock(side_effect=OSError("address in use"))
        assert not await meshtastic_tcp.async_setup_tcp_proxy(hass, entry)
    create_flow.assert_not_called()


async def test_announcement_failure_keeps_proxy_running(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    with (
        patch.object(meshtastic_tcp, "MeshtasticTcpProxy") as proxy,
        patch.object(meshtastic_tcp, "async_get_integration", AsyncMock(side_effect=RuntimeError("boom"))),
    ):
        proxy.return_value.start = AsyncMock()
        proxy.return_value.stop = AsyncMock()
        assert await meshtastic_tcp.async_setup_tcp_proxy(hass, entry)
        assert await meshtastic_tcp.async_unload_tcp_proxy(hass, entry)


def test_node_id() -> None:
    assert meshtastic_tcp._node_id(GATEWAY) == "!2a92ae57"
    assert meshtastic_tcp._node_id({"num": 0x8FA63860}) == "!8fa63860"
    assert meshtastic_tcp._node_id({}) is None
    assert meshtastic_tcp._node_id(None) is None
