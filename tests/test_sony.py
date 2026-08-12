"""Tests for the Sony AVR protocol client.

These exercise the client against a stub HTTP server rather than mocks, so the
SOAP envelopes and headers actually go over a socket and get parsed back.
"""

from __future__ import annotations

import base64

import aiohttp
import pytest
from aiohttp import web
from sony_avr_protocol.sony import (
    AuthResult,
    CannotConnect,
    PairingModeRequired,
    SonyAvrClient,
    SonyAvrError,
    _findtext,
    _parse_didl_title,
    _parse_xml,
    generate_device_id,
)

# Home Assistant's test plugin blocks sockets globally. These tests deliberately
# run a real HTTP server on loopback so the SOAP envelopes and headers are
# exercised over an actual connection, so opt back in.
pytestmark = pytest.mark.enable_socket

STATUS_XML = """<?xml version="1.0"?>
<statusList>
  <status name="power" value="active"/>
  <status name="viewing">
    <statusItem field="source" value="BD/DVD"/>
    <statusItem field="title" value="Test Title"/>
  </status>
</statusList>
"""


def soap_response(body: str, service: str = "RenderingControl") -> str:
    """Build a SOAP response the way the receiver does, prefix declarations included."""
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        f'xmlns:u="urn:schemas-upnp-org:service:{service}:1">'
        f"<s:Body>{body}</s:Body></s:Envelope>"
    )


class FakeReceiver:
    """A stub STR-DN840 that records what it was sent."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.headers: list[dict[str, str]] = []
        self.bodies: list[str] = []
        self.registered = False
        self.volume = 42
        self.muted = False
        self.transport_state = "PLAYING"
        self.require_pin = True
        self.reject_all_pins = False
        self.auth_header: str | None = None
        # Overrides for the status codes the receiver can return.
        self.register_status: int | None = None
        self.status_code = 200

    async def handle_register(self, request: web.Request) -> web.Response:
        self.requests.append(("register", request.path_qs))
        if self.register_status is not None:
            return web.Response(status=self.register_status)
        auth = request.headers.get("Authorization")
        if self.reject_all_pins or (self.require_pin and not auth):
            return web.Response(status=401)
        self.auth_header = auth
        self.registered = True
        return web.Response(status=200, text="OK")

    async def handle_status(self, request: web.Request) -> web.Response:
        self.requests.append(("status", request.path))
        if self.status_code != 200:
            return web.Response(status=self.status_code)
        return web.Response(status=200, text=STATUS_XML, content_type="text/xml")

    async def handle_ircc(self, request: web.Request) -> web.Response:
        body = await request.text()
        self.requests.append(("ircc", request.path))
        self.headers.append(dict(request.headers))
        self.bodies.append(body)
        return web.Response(
            status=200, text=soap_response("<u:X_SendIRCCResponse/>", "IRCC")
        )

    async def handle_rendering(self, request: web.Request) -> web.Response:
        body = await request.text()
        self.requests.append(("rendering", request.path))
        if "GetVolume" in body:
            return web.Response(
                status=200,
                text=soap_response(
                    f"<u:GetVolumeResponse><CurrentVolume>{self.volume}"
                    "</CurrentVolume></u:GetVolumeResponse>"
                ),
            )
        if "GetMute" in body:
            return web.Response(
                status=200,
                text=soap_response(
                    f"<u:GetMuteResponse><CurrentMute>{int(self.muted)}"
                    "</CurrentMute></u:GetMuteResponse>"
                ),
            )
        if "SetVolume" in body:
            start = body.index("<DesiredVolume>") + len("<DesiredVolume>")
            self.volume = int(body[start : body.index("</DesiredVolume>")])
            return web.Response(
                status=200, text=soap_response("<u:SetVolumeResponse/>")
            )
        if "SetMute" in body:
            start = body.index("<DesiredMute>") + len("<DesiredMute>")
            self.muted = body[start : body.index("</DesiredMute>")] == "1"
            return web.Response(status=200, text=soap_response("<u:SetMuteResponse/>"))
        return web.Response(status=500)

    async def handle_avtransport(self, request: web.Request) -> web.Response:
        body = await request.text()
        self.requests.append(("avtransport", request.path))
        if "GetTransportInfo" in body:
            return web.Response(
                status=200,
                text=soap_response(
                    "<u:GetTransportInfoResponse><CurrentTransportState>"
                    f"{self.transport_state}"
                    "</CurrentTransportState></u:GetTransportInfoResponse>",
                    "AVTransport",
                ),
            )
        return web.Response(
            status=200,
            text=soap_response(
                "<u:GetPositionInfoResponse><TrackMetaData></TrackMetaData>"
                "</u:GetPositionInfoResponse>",
                "AVTransport",
            ),
        )


@pytest.fixture
async def receiver(aiohttp_server):
    """Run a stub receiver and return (stub, client)."""
    stub = FakeReceiver()
    app = web.Application()
    app.router.add_get("/cers/register", stub.handle_register)
    app.router.add_get("/cers/getStatus", stub.handle_status)
    # Paths as advertised by a real STR-DN840's description.xml.
    app.router.add_post("/upnp/control/IRCC", stub.handle_ircc)
    app.router.add_post("/RenderingControl/ctrl", stub.handle_rendering)
    app.router.add_post("/AVTransport/ctrl", stub.handle_avtransport)

    server = await aiohttp_server(app)
    async with aiohttp.ClientSession() as session:
        client = SonyAvrClient(
            server.host,
            session,
            device_id="MediaRemote:AA:BB:CC:DD:EE:FF",
            cers_port=server.port,
            ircc_port=server.port,
            dmr_port=server.port,
        )
        yield stub, client


async def test_register_requests_pin_first(receiver) -> None:
    """A receiver that wants a PIN reports PIN_NEEDED, not an error."""
    stub, client = receiver
    assert await client.async_register() is AuthResult.PIN_NEEDED
    assert not stub.registered


async def test_register_succeeds_with_pin(receiver) -> None:
    """Supplying the PIN completes pairing."""
    stub, client = receiver
    assert await client.async_register() is AuthResult.PIN_NEEDED
    assert await client.async_register("1234") is AuthResult.SUCCESS

    # The PIN is sent as basic auth with an empty username.
    assert stub.auth_header == f"Basic {base64.b64encode(b':1234').decode()}"


async def test_register_rejects_bad_pin(receiver) -> None:
    """A PIN the receiver refuses is an error, not a second PIN prompt."""
    stub, client = receiver
    stub.reject_all_pins = True
    assert await client.async_register("0000") is AuthResult.ERROR


async def test_register_reports_pairing_mode_required(receiver) -> None:
    """A 406 means the receiver needs to be put into pairing mode.

    The STR-DN840 answers 406 unless the user has the device-registration
    screen open, which is a different problem from being unreachable and needs
    a different message.
    """
    stub, client = receiver
    stub.register_status = 406

    with pytest.raises(PairingModeRequired):
        await client.async_register()


async def test_device_id_is_url_encoded(receiver) -> None:
    """The colons in the device id must be percent-encoded.

    Sent raw they truncate the query string and the receiver drops the
    connection without replying.
    """
    stub, client = receiver
    stub.require_pin = False
    await client.async_register()

    _, query = stub.requests[0]
    assert "%3A" in query
    assert "deviceId=MediaRemote%3A" in query


async def test_status_available_when_unregistered(receiver) -> None:
    """An unregistered receiver is still reachable, and still reports volume.

    getStatus answers 400 until registration, but the UPnP services work
    regardless, so the entity should not go unavailable.
    """
    stub, client = receiver
    stub.status_code = 400
    stub.volume = 39

    status = await client.async_get_status()
    assert status.available is True
    assert status.volume == 39
    assert status.transport_state == "PLAYING"


async def test_register_without_pin_when_not_required(receiver) -> None:
    """Receivers that pair silently return SUCCESS on the first call."""
    stub, client = receiver
    stub.require_pin = False
    assert await client.async_register() is AuthResult.SUCCESS


async def test_send_command_uses_lowercase_soapaction(receiver) -> None:
    """The DN8xx firmware only matches a lowercase soapaction header."""
    stub, client = receiver
    await client.async_send_command("volume_up")

    headers = stub.headers[0]
    assert "soapaction" in {k.lower() for k in headers}
    assert "X_SendIRCC" in headers.get("soapaction", "")
    assert "AAAAAgAAADAAAAASAw==" in stub.bodies[0]


async def test_send_unknown_command_raises(receiver) -> None:
    """An unrecognised command name is a programming error, not a no-op."""
    _, client = receiver
    with pytest.raises(SonyAvrError, match="Unknown IRCC command"):
        await client.async_send_command("does_not_exist")


async def test_select_unknown_source_raises(receiver) -> None:
    """Selecting an input we have no code for raises."""
    _, client = receiver
    with pytest.raises(SonyAvrError, match="Unknown input"):
        await client.async_select_source("Betamax")


async def test_get_volume_and_mute(receiver) -> None:
    """Volume and mute come back from RenderingControl."""
    stub, client = receiver
    stub.volume = 55
    stub.muted = True
    volume, muted = await client.async_get_volume()
    assert volume == 55
    assert muted is True


async def test_set_volume_clamps(receiver) -> None:
    """Out-of-range volumes are clamped rather than sent verbatim."""
    stub, client = receiver
    await client.async_set_volume(150)
    assert stub.volume == 100
    await client.async_set_volume(-10)
    assert stub.volume == 0


async def test_set_mute(receiver) -> None:
    """Mute round-trips through SetMute."""
    stub, client = receiver
    await client.async_set_mute(True)
    assert stub.muted is True


async def test_get_status_parses_source_and_title(receiver) -> None:
    """A full status poll yields power, source, volume and transport state."""
    stub, client = receiver
    stub.volume = 30
    status = await client.async_get_status()

    assert status.available is True
    assert status.power_on is True
    assert status.source == "BD/DVD"
    assert status.media_title == "Test Title"
    assert status.volume == 30
    assert status.transport_state == "PLAYING"


async def test_status_when_receiver_is_asleep() -> None:
    """A receiver in standby is unavailable, not an exception."""
    async with aiohttp.ClientSession() as session:
        client = SonyAvrClient(
            "127.0.0.1",
            session,
            device_id="test",
            # Nothing is listening here.
            cers_port=9,
            ircc_port=9,
            dmr_port=9,
        )
        status = await client.async_get_status()
        assert status.available is False
        assert status.power_on is False


async def test_command_to_asleep_receiver_raises() -> None:
    """Commands to an unreachable receiver raise CannotConnect."""
    async with aiohttp.ClientSession() as session:
        client = SonyAvrClient(
            "127.0.0.1", session, device_id="test", ircc_port=9, cers_port=9, dmr_port=9
        )
        with pytest.raises(CannotConnect):
            await client.async_send_command("power_on")


def test_generate_device_id_is_unique_and_shaped() -> None:
    """Device ids look like Sony expects and do not collide."""
    first = generate_device_id()
    second = generate_device_id()
    assert first.startswith("MediaRemote:")
    assert first != second
    assert len(first.split(":")) == 7


def test_parse_xml_recovers_from_undeclared_prefix() -> None:
    """Responses using a prefix they never declare are still readable."""
    malformed = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        "<s:Body><u:GetVolumeResponse><CurrentVolume>17</CurrentVolume>"
        "</u:GetVolumeResponse></s:Body></s:Envelope>"
    )
    root = _parse_xml(malformed)
    assert root is not None
    assert _findtext(root, "CurrentVolume") == "17"


def test_parse_xml_rejects_real_garbage() -> None:
    """Genuinely unparsable input still yields None."""
    assert _parse_xml("<<<not xml at all") is None


def test_parse_didl_title() -> None:
    """Track titles are pulled out of DIDL-Lite metadata."""
    didl = (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<item><dc:title>Song Name</dc:title></item></DIDL-Lite>"
    )
    assert _parse_didl_title(didl) == "Song Name"
    assert _parse_didl_title("not xml") is None
