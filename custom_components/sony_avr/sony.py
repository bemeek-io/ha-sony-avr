"""Async client for Sony AV receivers using IRCC-IP and UPnP.

This talks to the receiver the way the TV SideView app does. Verified against
an STR-DN840 running firmware JB3.1.1:

* ``/cers/register`` on port 50001 performs the one-time pairing. This
  generation registers in "mode 1", which has no PIN at all -- but it only
  accepts a registration while the user has the device-registration screen
  open on the receiver, and answers 406 otherwise.
* ``/upnp/control/IRCC`` accepts ``X_SendIRCC`` SOAP calls carrying a
  base64 key code -- the same codes the physical remote emits.
* ``/RenderingControl/ctrl`` (volume, mute) and ``/AVTransport/ctrl``
  (transport state) are how state is read back rather than guessed.

Note that only registration lives on 50001; IRCC and the UPnP services are all
served from port 8080, at the paths the device description advertises rather
than the ``/upnp/control/<Service>`` layout Sony's TVs use.

The receiver is not a well-behaved HTTP server: it wants a lowercase
``soapaction`` header, closes connections eagerly, rejects a device id whose
colons are not percent-encoded by dropping the connection outright, and stops
listening a second or two after entering standby. Its CERS service will also
wedge -- accepting TCP but never replying -- after repeated rejected
registrations, and only a power cycle clears it.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree

import aiohttp

from .const import (
    AV_TRANSPORT_PATH,
    CLIENT_NAME,
    CLIENT_TYPE,
    DEFAULT_CERS_PORT,
    DEFAULT_DMR_PORT,
    DEFAULT_IRCC_PORT,
    IRCC_CONTROL_PATH,
    RENDERING_CONTROL_PATH,
    REQUEST_TIMEOUT,
)
from .ircc_codes import INPUT_CODES, IRCC_CODES

_LOGGER = logging.getLogger(__name__)

SOAP_ENCODING = "http://schemas.xmlsoap.org/soap/encoding/"
SOAP_ENVELOPE_NS = "http://schemas.xmlsoap.org/soap/envelope/"

IRCC_SERVICE = "urn:schemas-sony-com:service:IRCC:1"
RENDERING_CONTROL_SERVICE = "urn:schemas-upnp-org:service:RenderingControl:1"
AV_TRANSPORT_SERVICE = "urn:schemas-upnp-org:service:AVTransport:1"

# The receiver's RenderingControl reports volume on a 0-100 scale.
MAX_VOLUME = 100


class AuthResult(Enum):
    """Outcome of a registration attempt."""

    SUCCESS = "success"
    PIN_NEEDED = "pin_needed"
    ERROR = "error"


class SonyAvrError(Exception):
    """Base error for this client."""


class CannotConnect(SonyAvrError):
    """The receiver did not answer. Usually means it is in standby."""


class InvalidAuth(SonyAvrError):
    """The receiver rejected our credentials or PIN."""


class PairingModeRequired(SonyAvrError):
    """The receiver refused to pair until it is put into pairing mode.

    The DN8xx generation will not accept a registration unless the user has
    opened the device-registration screen on the receiver itself.
    """


@dataclass
class SonyStatus:
    """A snapshot of the receiver's state."""

    available: bool = False
    power_on: bool = False
    volume: int | None = None
    muted: bool | None = None
    transport_state: str | None = None
    source: str | None = None
    media_title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _soap_envelope(service: str, action: str, body: str) -> str:
    """Wrap a SOAP action body in the envelope the receiver expects."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_ENVELOPE_NS}" '
        f's:encodingStyle="{SOAP_ENCODING}">'
        "<s:Body>"
        f'<u:{action} xmlns:u="{service}">{body}</u:{action}>'
        "</s:Body>"
        "</s:Envelope>"
    )


def _parse_xml(text: str) -> ElementTree.Element | None:
    """Parse XML, tolerating the malformed documents this firmware emits.

    Some responses reference a namespace prefix they never declare, which is
    fatal to a strict parser. Rather than lose the whole payload, retry with
    the offending prefixes stripped.
    """
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError as err:
        if "unbound prefix" not in str(err):
            return None

    stripped = re.sub(r"<(/?)[A-Za-z0-9_.-]+:", r"<\1", text)
    try:
        return ElementTree.fromstring(stripped)
    except ElementTree.ParseError:
        return None


async def _raw_status(
    host: str, port: int, target: str, headers: dict[str, str]
) -> int:
    """Fetch just the HTTP status code over a bare socket.

    The receiver's error responses are truncated: it sends the status line and
    some headers, then closes without the blank line that ends the header
    block. aiohttp's parser treats that as a disconnect and discards the
    response, so the status -- which is the only part we need -- is read here
    by hand instead.
    """
    request = f"GET {target} HTTP/1.1\r\nHost: {host}:{port}\r\n"
    for key, value in headers.items():
        request += f"{key}: {value}\r\n"
    request += "\r\n"

    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(request.encode())
        await writer.drain()
        status_line = await reader.readline()
    finally:
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()

    parts = status_line.decode("ascii", "replace").split()
    if len(parts) < 2 or not parts[1].isdigit():
        raise CannotConnect(f"Malformed response from {host}: {status_line!r}")
    return int(parts[1])


def _findtext(root: ElementTree.Element, tag: str) -> str | None:
    """Find the first element with a local name of *tag*, ignoring namespaces.

    The receiver is inconsistent about namespacing its responses, so matching
    on the local name is more reliable than a qualified lookup.
    """
    for element in root.iter():
        if element.tag.rpartition("}")[2] == tag:
            return element.text
    return None


class SonyAvrClient:
    """Controls a single Sony AV receiver."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        device_id: str,
        cers_port: int = DEFAULT_CERS_PORT,
        ircc_port: int = DEFAULT_IRCC_PORT,
        dmr_port: int = DEFAULT_DMR_PORT,
    ) -> None:
        """Initialise the client. *device_id* must be stable across restarts."""
        self._host = host
        self._session = session
        self._device_id = device_id
        self._cers_port = cers_port
        self._ircc_port = ircc_port
        self._dmr_port = dmr_port
        self._timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    @property
    def host(self) -> str:
        """The receiver's address."""
        return self._host

    @property
    def device_id(self) -> str:
        """The client identity registered with the receiver."""
        return self._device_id

    def _cers_headers(self) -> dict[str, str]:
        """Headers identifying us to the CERS endpoints."""
        return {
            "X-CERS-DEVICE-ID": self._device_id,
            "X-CERS-DEVICE-INFO": f"{CLIENT_TYPE}/{CLIENT_NAME}",
            "Connection": "close",
        }

    async def async_register(self, pin: str | None = None) -> AuthResult:
        """Pair with the receiver.

        Two registration modes exist in this family. Mode 3 devices show a PIN
        and answer 401 until it is supplied. Mode 1 devices -- including the
        STR-DN840 -- have no PIN at all and simply answer 200, but only while
        the user has the registration screen open on the receiver; otherwise
        they answer 406.
        """
        # The colons must be percent-encoded; sent raw they truncate the query
        # and the receiver drops the connection without replying.
        target = (
            "/cers/register"
            f"?name={quote(CLIENT_NAME, safe='')}&registrationType=initial"
            f"&deviceId={quote(self._device_id, safe='')}"
        )
        headers = self._cers_headers()
        if pin:
            # The PIN goes in as basic auth with an empty username. Built by
            # hand because aiohttp's BasicAuth helper is going away in 4.0.
            token = base64.b64encode(f":{pin}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {token}"

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                status = await _raw_status(self._host, self._cers_port, target, headers)
        except (TimeoutError, OSError) as err:
            raise CannotConnect(
                f"Could not reach {self._host}; is the receiver powered on?"
            ) from err

        if status == 200:
            return AuthResult.SUCCESS
        # 401 on the first call is the receiver telling us it has put a PIN on
        # screen and is waiting for it.
        if status == 401:
            return AuthResult.ERROR if pin else AuthResult.PIN_NEEDED
        if status == 406:
            raise PairingModeRequired(
                "The receiver refused the pairing request. Open "
                "Settings > Network > Device Registration on the "
                "receiver, choose to add a device, and try again."
            )
        _LOGGER.debug("Registration returned unexpected status %s", status)
        return AuthResult.ERROR

    async def async_send_command(self, command: str) -> None:
        """Send a named IRCC command from :data:`IRCC_CODES`."""
        code = IRCC_CODES.get(command)
        if code is None:
            raise SonyAvrError(f"Unknown IRCC command: {command}")
        await self.async_send_code(code)

    async def async_select_source(self, source: str) -> None:
        """Switch the receiver to a named input."""
        code = INPUT_CODES.get(source)
        if code is None:
            raise SonyAvrError(f"Unknown input: {source}")
        await self.async_send_code(code)

    async def async_send_code(self, code: str) -> None:
        """Send a raw base64 IRCC key code."""
        url = f"http://{self._host}:{self._ircc_port}{IRCC_CONTROL_PATH}"
        body = _soap_envelope(
            IRCC_SERVICE, "X_SendIRCC", f"<IRCCCode>{code}</IRCCCode>"
        )
        headers = {
            # Lowercase intentionally: the DN8xx/DN10xx firmware fails to match
            # the canonical "SOAPAction" spelling.
            "soapaction": f'"{IRCC_SERVICE}#X_SendIRCC"',
            "content-type": "text/xml; charset=utf-8",
            **self._cers_headers(),
        }

        try:
            async with self._session.post(
                url, data=body.encode("utf-8"), headers=headers, timeout=self._timeout
            ) as response:
                if response.status == 401:
                    raise InvalidAuth("Receiver rejected the command; re-pair needed")
                if response.status != 200:
                    raise SonyAvrError(
                        f"IRCC command failed with status {response.status}"
                    )
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(f"Could not send command to {self._host}") from err

    async def _async_soap(
        self, service: str, action: str, body: str, path: str
    ) -> ElementTree.Element | None:
        """Call a UPnP SOAP action on the DLNA renderer, or None if unreachable."""
        url = f"http://{self._host}:{self._dmr_port}{path}"
        envelope = _soap_envelope(service, action, body)
        headers = {
            "soapaction": f'"{service}#{action}"',
            "content-type": "text/xml; charset=utf-8",
            "Connection": "close",
        }

        try:
            async with self._session.post(
                url,
                data=envelope.encode("utf-8"),
                headers=headers,
                timeout=self._timeout,
            ) as response:
                if response.status != 200:
                    return None
                text = await response.text()
        except (TimeoutError, aiohttp.ClientError):
            return None

        root = _parse_xml(text)
        if root is None:
            _LOGGER.debug("Could not parse SOAP response for %s", action)
        return root

    async def async_get_volume(self) -> tuple[int | None, bool | None]:
        """Read volume (0-100) and mute state from RenderingControl."""
        volume: int | None = None
        muted: bool | None = None

        root = await self._async_soap(
            RENDERING_CONTROL_SERVICE,
            "GetVolume",
            "<InstanceID>0</InstanceID><Channel>Master</Channel>",
            RENDERING_CONTROL_PATH,
        )
        if root is not None and (text := _findtext(root, "CurrentVolume")):
            try:
                volume = int(text)
            except ValueError:
                _LOGGER.debug("Unparsable volume value: %s", text)

        root = await self._async_soap(
            RENDERING_CONTROL_SERVICE,
            "GetMute",
            "<InstanceID>0</InstanceID><Channel>Master</Channel>",
            RENDERING_CONTROL_PATH,
        )
        if root is not None and (text := _findtext(root, "CurrentMute")):
            muted = text in ("1", "true", "True")

        return volume, muted

    async def async_set_volume(self, volume: int) -> None:
        """Set absolute volume (0-100) via RenderingControl."""
        volume = max(0, min(MAX_VOLUME, int(volume)))
        result = await self._async_soap(
            RENDERING_CONTROL_SERVICE,
            "SetVolume",
            "<InstanceID>0</InstanceID><Channel>Master</Channel>"
            f"<DesiredVolume>{volume}</DesiredVolume>",
            RENDERING_CONTROL_PATH,
        )
        if result is None:
            raise CannotConnect("Could not set volume; receiver did not respond")

    async def async_set_mute(self, mute: bool) -> None:
        """Set mute via RenderingControl, falling back to the IRCC toggle."""
        result = await self._async_soap(
            RENDERING_CONTROL_SERVICE,
            "SetMute",
            "<InstanceID>0</InstanceID><Channel>Master</Channel>"
            f"<DesiredMute>{1 if mute else 0}</DesiredMute>",
            RENDERING_CONTROL_PATH,
        )
        if result is None:
            # Some firmware revisions reject SetMute but honour the remote key.
            await self.async_send_command("mute")

    async def async_get_transport_info(self) -> tuple[str | None, str | None]:
        """Read transport state and current track title from AVTransport."""
        state: str | None = None
        title: str | None = None

        root = await self._async_soap(
            AV_TRANSPORT_SERVICE,
            "GetTransportInfo",
            "<InstanceID>0</InstanceID>",
            AV_TRANSPORT_PATH,
        )
        if root is not None:
            state = _findtext(root, "CurrentTransportState")

        root = await self._async_soap(
            AV_TRANSPORT_SERVICE,
            "GetPositionInfo",
            "<InstanceID>0</InstanceID>",
            AV_TRANSPORT_PATH,
        )
        if root is not None and (metadata := _findtext(root, "TrackMetaData")):
            title = _parse_didl_title(metadata)

        return state, title

    async def async_get_status(self) -> SonyStatus:
        """Poll the receiver for a full state snapshot.

        An unreachable receiver is reported as unavailable rather than raising,
        since standby is indistinguishable from being switched off at the wall.

        Availability is judged by whether the receiver answers at all, not by
        whether ``getStatus`` succeeds: that endpoint returns 400 until the
        client has been registered, and an unregistered-but-awake receiver is
        still very much reachable.
        """
        url = f"http://{self._host}:{self._cers_port}/cers/getStatus"

        try:
            async with self._session.get(
                url, headers=self._cers_headers(), timeout=self._timeout
            ) as response:
                if response.status == 401:
                    raise InvalidAuth("Receiver no longer trusts this client")
                text = await response.text() if response.status == 200 else None
        except aiohttp.ClientResponseError:
            raise
        except (TimeoutError, aiohttp.ClientError):
            # Unregistered clients get a truncated 403 that aiohttp cannot
            # parse. That is not the same as being unreachable, so fall back to
            # reading the bare status before giving up on the receiver.
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    status_code = await _raw_status(
                        self._host,
                        self._cers_port,
                        "/cers/getStatus",
                        self._cers_headers(),
                    )
            except (TimeoutError, OSError, CannotConnect):
                return SonyStatus(available=False)

            if status_code == 401:
                raise InvalidAuth("Receiver no longer trusts this client") from None
            text = None

        status = SonyStatus(available=True, power_on=True)

        # Without registration there is no status document, but volume and
        # transport still read fine over UPnP, so carry on and fill those in.
        root = _parse_xml(text) if text else None
        if root is None:
            status.volume, status.muted = await self.async_get_volume()
            status.transport_state, title = await self.async_get_transport_info()
            status.media_title = title
            return status

        for element in root.iter():
            if element.tag.rpartition("}")[2] != "status":
                continue
            name = element.get("name")
            if name == "viewing":
                for item in element:
                    if item.get("field") == "source":
                        status.source = item.get("value")
                    elif item.get("field") == "title":
                        status.media_title = item.get("value")
            elif name == "power":
                status.power_on = element.get("value") != "off"

        status.volume, status.muted = await self.async_get_volume()
        transport_state, title = await self.async_get_transport_info()
        status.transport_state = transport_state
        if title and not status.media_title:
            status.media_title = title

        return status

    async def async_turn_on(self) -> None:
        """Wake the receiver.

        Only works when the receiver's network standby setting keeps its
        network interface alive; otherwise nothing is listening to hear this.
        """
        await self.async_send_command("power_on")

    async def async_turn_off(self) -> None:
        """Put the receiver into standby."""
        await self.async_send_command("power_off")


def _parse_didl_title(metadata: str) -> str | None:
    """Pull the track title out of a DIDL-Lite metadata document."""
    root = _parse_xml(metadata)
    if root is None:
        return None
    return _findtext(root, "title")


def generate_device_id() -> str:
    """Build a stable client id for registration.

    The receiver expects ``MediaRemote:`` followed by a colon-separated
    MAC-shaped value, and rejects other shapes outright. A random value is
    fine as long as it never changes, since the receiver keys its pairing
    table on this id.
    """
    import uuid

    raw = uuid.uuid4().bytes[:6]
    mac = ":".join(f"{b:02X}" for b in raw)
    return f"MediaRemote:{mac}"


def encode_ircc(raw: bytes) -> str:
    """Base64-encode a raw IRCC payload. Useful for adding new key codes."""
    return base64.b64encode(raw).decode("ascii")
