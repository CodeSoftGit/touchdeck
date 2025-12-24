from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from touchdeck.utils import MediaState


@dataclass(slots=True)
class MediaDevice:
    id: str
    name: str
    type: str = ""
    is_active: bool = False
    volume_percent: int | None = None


class MediaError(Exception):
    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.user_message = message
        self.recoverable = recoverable


class MediaProvider:
    name: str = "unknown"

    async def get_state(self) -> MediaState:
        raise NotImplementedError

    async def play_pause(self) -> None:
        raise NotImplementedError

    async def next(self) -> None:
        raise NotImplementedError

    async def previous(self) -> None:
        raise NotImplementedError

    async def seek(self, position_ms: int) -> None:
        raise NotImplementedError

    async def set_volume(self, percent: int) -> None:
        raise NotImplementedError

    async def list_devices(self) -> list[MediaDevice]:
        return []

    async def transfer_playback(self, device_id: str, *, play: bool = True) -> None:
        return None

    async def ensure_ready(self) -> None:
        """Optional hook for providers that require warm-up (e.g., auth refresh)."""
        return None


class MediaManager:
    def __init__(
        self,
        providers: dict[str, MediaProvider],
        settings_source: Callable[[], str],
    ) -> None:
        self._providers = providers
        self._settings_source = settings_source
        self._lock = asyncio.Lock()

    def _provider(self) -> MediaProvider:
        key = (self._settings_source() or "mpris").lower()
        return self._providers.get(key) or next(iter(self._providers.values()))

    async def get_state(self) -> MediaState:
        provider = self._provider()
        try:
            state = await provider.get_state()
            state.source = self._settings_source()
            return state
        except MediaError as exc:
            return MediaState(source=self._settings_source(), status="Error", message=exc.user_message)
        except Exception:
            return MediaState(source=self._settings_source())

    async def play_pause(self) -> str | None:
        return await self._run_action(lambda p: p.play_pause())

    async def next(self) -> str | None:
        return await self._run_action(lambda p: p.next())

    async def previous(self) -> str | None:
        return await self._run_action(lambda p: p.previous())

    async def seek(self, position_ms: int) -> str | None:
        return await self._run_action(lambda p: p.seek(position_ms))

    async def set_volume(self, percent: int) -> str | None:
        return await self._run_action(lambda p: p.set_volume(percent))

    async def list_devices(self) -> list[MediaDevice]:
        try:
            return await self._provider().list_devices()
        except Exception:
            return []

    async def transfer_playback(self, device_id: str, *, play: bool = True) -> str | None:
        return await self._run_action(lambda p: p.transfer_playback(device_id, play=play))

    async def ensure_ready(self) -> str | None:
        try:
            await self._provider().ensure_ready()
            return None
        except MediaError as exc:
            return exc.user_message
        except Exception:
            return "Media provider not ready"

    async def _run_action(self, fn: Callable[[MediaProvider], Awaitable[None]]) -> str | None:
        provider = self._provider()
        try:
            async with self._lock:
                await fn(provider)
            return None
        except MediaError as exc:
            return exc.user_message
        except Exception:
            return "Media control failed"