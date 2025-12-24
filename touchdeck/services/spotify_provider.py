from __future__ import annotations

import asyncio
import queue
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from spotipy import Spotify
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from touchdeck.media import MediaDevice, MediaError, MediaProvider
from touchdeck.utils import MediaState


_AUTH_SCOPE = "user-read-playback-state user-read-currently-playing user-modify-playback-state"


@dataclass(slots=True)
class _AuthResult:
    code: str | None = None
    state: str | None = None


class SpotifyProvider(MediaProvider):
    name = "spotify"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_port: int,
        device_id: str | None,
        cache_path: Path,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_port = redirect_port
        self._device_id = device_id
        self._cache_path = cache_path
        self._auth: SpotifyOAuth | None = None
        self._client: Spotify | None = None
        self._lock = asyncio.Lock()

    def update_config(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_port: int,
        device_id: str | None,
        cache_path: Path | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_port = redirect_port
        self._device_id = device_id
        if cache_path is not None:
            self._cache_path = cache_path
        self._auth = None
        self._client = None

    async def ensure_ready(self) -> None:
        await self._get_client()

    async def authenticate(self) -> None:
        auth = self._build_auth_manager()
        url = await asyncio.to_thread(auth.get_authorize_url)
        code = await self._capture_code(url)
        if not code:
            raise MediaError("Spotify sign-in was canceled")
        await asyncio.to_thread(auth.get_access_token, code, True)
        self._auth = auth
        self._client = Spotify(auth_manager=auth, requests_timeout=10, retries=1)

    async def get_state(self) -> MediaState:
        client = await self._get_client()
        if client is None:
            return MediaState(source="spotify", status="Stopped")
        try:
            playback = await asyncio.to_thread(client.current_playback)
        except SpotifyException as exc:
            raise self._translate_error(exc)
        if not playback:
            return MediaState(source="spotify", status="Stopped")

        is_playing = bool(playback.get("is_playing"))
        device = playback.get("device") or {}
        track = playback.get("item") or {}
        artists = track.get("artists") or []
        artist_name = ", ".join([a.get("name", "") for a in artists if isinstance(a, dict)])
        album_info = track.get("album") or {}
        album = album_info.get("name") or ""
        images = album_info.get("images") or []
        art_url = images[0].get("url") if images else None

        # Fallback fetch for cover art when the playback payload omits images
        if not art_url:
            art_url = await self._fetch_playing_art_url()

        return MediaState(
            source="spotify",
            title=track.get("name") or "Nothing Playing",
            artist=artist_name,
            album=album,
            art_url=art_url,
            is_playing=is_playing,
            progress_ms=playback.get("progress_ms") or 0,
            duration_ms=track.get("duration_ms") or 0,
            device_name=device.get("name") or "",
            volume_percent=device.get("volume_percent"),
            can_seek=True,
            can_control=True,
            track_id=track.get("id") or track.get("uri"),
            status="Playing" if is_playing else "Paused",
        )

    async def play_pause(self) -> None:
        client = await self._get_client()
        playback = await asyncio.to_thread(client.current_playback)
        is_playing = bool(playback.get("is_playing")) if playback else False
        try:
            if is_playing:
                await asyncio.to_thread(client.pause_playback, device_id=self._device_id)
            else:
                await asyncio.to_thread(client.start_playback, device_id=self._device_id)
        except SpotifyException as exc:
            raise self._translate_error(exc)

    async def next(self) -> None:
        client = await self._get_client()
        try:
            await asyncio.to_thread(client.next_track, device_id=self._device_id)
        except SpotifyException as exc:
            raise self._translate_error(exc)

    async def previous(self) -> None:
        client = await self._get_client()
        try:
            await asyncio.to_thread(client.previous_track, device_id=self._device_id)
        except SpotifyException as exc:
            raise self._translate_error(exc)

    async def seek(self, position_ms: int) -> None:
        client = await self._get_client()
        try:
            await asyncio.to_thread(client.seek_track, position_ms, device_id=self._device_id)
        except SpotifyException as exc:
            raise self._translate_error(exc)

    async def set_volume(self, percent: int) -> None:
        client = await self._get_client()
        try:
            await asyncio.to_thread(
                client.volume, max(0, min(100, int(percent))), self._device_id
            )
        except SpotifyException as exc:
            raise self._translate_error(exc)

    async def list_devices(self) -> list[MediaDevice]:
        client = await self._get_client()
        try:
            data = await asyncio.to_thread(client.devices)
        except SpotifyException as exc:
            raise self._translate_error(exc)
        devices = []
        for d in data.get("devices", []):
            device_id = d.get("id")
            name = d.get("name")
            if not device_id or not name:
                continue
            devices.append(
                MediaDevice(
                    id=device_id,
                    name=name,
                    type=d.get("type") or "",
                    is_active=bool(d.get("is_active")),
                    volume_percent=d.get("volume_percent"),
                )
            )
        return devices

    async def transfer_playback(self, device_id: str, *, play: bool = True) -> None:
        client = await self._get_client()
        try:
            await asyncio.to_thread(client.transfer_playback, device_id, force_play=play)
            self._device_id = device_id
        except SpotifyException as exc:
            raise self._translate_error(exc)

    async def _get_client(self) -> Spotify:
        async with self._lock:
            auth = self._auth or self._build_auth_manager()
            token = await asyncio.to_thread(auth.get_cached_token)
            if token and not auth.is_token_expired(token):
                self._auth = auth
                if self._client is None:
                    self._client = Spotify(auth_manager=auth, requests_timeout=10, retries=1)
                return self._client

            if token and token.get("refresh_token"):
                refreshed = await asyncio.to_thread(auth.refresh_access_token, token["refresh_token"])
                if refreshed:
                    self._auth = auth
                    self._client = Spotify(auth_manager=auth, requests_timeout=10, retries=1)
                    return self._client

            raise MediaError("Spotify is not signed in")

    async def _fetch_playing_art_url(self) -> str | None:
        """Attempt a secondary lookup for the current track's cover art."""
        client = await self._get_client()
        try:
            playing = await asyncio.to_thread(client.current_user_playing_track)
        except (SpotifyException, MediaError):
            return None
        if not playing:
            return None
        track = playing.get("item") or {}
        album_info = track.get("album") or {}
        images = album_info.get("images") or []
        return images[0].get("url") if images else None

    def _build_auth_manager(self) -> SpotifyOAuth:
        if not (self._client_id and self._client_secret):
            raise MediaError("Spotify credentials are missing")
        redirect_uri = f"http://127.0.0.1:{int(self._redirect_port)}/callback"
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        auth = SpotifyOAuth(
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=redirect_uri,
            scope=_AUTH_SCOPE,
            cache_path=str(self._cache_path),
            open_browser=False,
            show_dialog=False,
        )
        self._auth = auth
        return auth

    async def _capture_code(self, auth_url: str) -> str | None:
        result = _AuthResult()
        code_queue: queue.Queue[_AuthResult] = queue.Queue()

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args, **_kwargs) -> None:  # noqa: D401
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                result.code = (params.get("code") or [None])[0]
                result.state = (params.get("state") or [None])[0]
                message = "Spotify sign-in complete. You can close this window."
                body = message.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                code_queue.put(result)

        try:
            server = HTTPServer(("127.0.0.1", int(self._redirect_port)), _Handler)
        except OSError as exc:
            raise MediaError(f"Could not start local auth server: {exc}")

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        webbrowser.open(auth_url)
        try:
            waited = await asyncio.wait_for(asyncio.to_thread(code_queue.get), timeout=120)
            return waited.code
        except asyncio.TimeoutError:
            raise MediaError("Spotify sign-in timed out")
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def _translate_error(self, exc: SpotifyException) -> MediaError:
        msg = exc.msg or "Spotify error"
        if exc.http_status == 403 and "PREMIUM" in msg.upper():
            return MediaError("Spotify Premium is required for that control")
        if exc.http_status == 404 and "NO ACTIVE DEVICE" in msg.upper():
            return MediaError("No active Spotify device. Pick one in Settings -> Media.")
        return MediaError(msg)