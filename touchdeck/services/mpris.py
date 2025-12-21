from __future__ import annotations

import asyncio
from typing import Any

from dbus_next.aio import MessageBus
from dbus_next.message import Message
from dbus_next.constants import MessageType

from touchdeck.utils import NowPlaying, unvariant, first_str


DBUS_DEST = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
DBUS_IFACE = "org.freedesktop.DBus"

MPRIS_PATH = "/org/mpris/MediaPlayer2"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


class MprisService:
    """Minimal MPRIS client using low-level dbus-next calls.

    - Lists players by filtering bus names starting with `org.mpris.MediaPlayer2.`
    - Reads properties: PlaybackStatus, Metadata, Position, CanSeek
    - Calls methods: PlayPause, Next, Previous, SetPosition
    """

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._lock = asyncio.Lock()
        self._preferred: str | None = None

    async def _ensure_bus(self) -> MessageBus:
        if self._bus is None:
            self._bus = await MessageBus().connect()
        return self._bus

    async def _call(self, msg: Message) -> Any:
        bus = await self._ensure_bus()
        reply = await bus.call(msg)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(str(reply.body))
        return reply.body

    async def list_players(self) -> list[str]:
        body = await self._call(
            Message(
                destination=DBUS_DEST,
                path=DBUS_PATH,
                interface=DBUS_IFACE,
                member="ListNames",
            )
        )
        names = body[0]
        return [
            n
            for n in names
            if isinstance(n, str) and n.startswith("org.mpris.MediaPlayer2.")
        ]

    async def _get_prop(self, dest: str, iface: str, prop: str) -> Any:
        body = await self._call(
            Message(
                destination=dest,
                path=MPRIS_PATH,
                interface=PROPS_IFACE,
                member="Get",
                signature="ss",
                body=[iface, prop],
            )
        )
        # Get returns a single Variant
        return body[0].value

    async def _pick_player(self, names: list[str]) -> str | None:
        if not names:
            return None
        if self._preferred in names:
            return self._preferred
        # Prefer an actively playing player if possible.
        for n in names:
            try:
                status = await self._get_prop(n, PLAYER_IFACE, "PlaybackStatus")
                if status == "Playing":
                    self._preferred = n
                    return n
            except Exception:
                continue
        self._preferred = names[0]
        return names[0]

    async def now_playing(self) -> NowPlaying:
        async with self._lock:
            try:
                players = await self.list_players()
                name = await self._pick_player(players)
                if not name:
                    return NowPlaying()

                status: str = await self._get_prop(name, PLAYER_IFACE, "PlaybackStatus")
                meta: dict[str, Any] = (
                    await self._get_prop(name, PLAYER_IFACE, "Metadata") or {}
                )
                can_seek: bool = bool(
                    await self._get_prop(name, PLAYER_IFACE, "CanSeek")
                )
                # Position is in microseconds
                pos_us: int = int(
                    await self._get_prop(name, PLAYER_IFACE, "Position") or 0
                )

                title = first_str(meta.get("xesam:title")) or "Unknown Title"
                artist = first_str(meta.get("xesam:artist")) or "Unknown Artist"
                album = first_str(meta.get("xesam:album")) or ""

                length_us = int(unvariant(meta.get("mpris:length") or 0))
                art_url = first_str(meta.get("mpris:artUrl")) or None
                track_id = first_str(meta.get("mpris:trackid")) or None

                return NowPlaying(
                    bus_name=name,
                    status=status,
                    title=title,
                    artist=artist,
                    album=album,
                    art_url=art_url,
                    position_ms=pos_us // 1000,
                    length_ms=length_us // 1000,
                    can_seek=can_seek,
                    track_id=track_id,
                )
            except Exception:
                # Keep UI alive even if a player vanishes mid-poll.
                return NowPlaying()

    async def _call_player(
        self, dest: str, member: str, signature: str = "", body: list[Any] | None = None
    ) -> None:
        if not dest:
            return
        await self._call(
            Message(
                destination=dest,
                path=MPRIS_PATH,
                interface=PLAYER_IFACE,
                member=member,
                signature=signature,
                body=body or [],
            )
        )

    async def play_pause(self, dest: str) -> None:
        await self._call_player(dest, "PlayPause")

    async def next(self, dest: str) -> None:
        await self._call_player(dest, "Next")

    async def previous(self, dest: str) -> None:
        await self._call_player(dest, "Previous")

    async def set_position(self, dest: str, track_id: str, position_ms: int) -> None:
        # MPRIS SetPosition expects TrackId (object path) and Position (microseconds)
        await self._call_player(
            dest,
            "SetPosition",
            signature="ox",
            body=[track_id, int(position_ms) * 1000],
        )
