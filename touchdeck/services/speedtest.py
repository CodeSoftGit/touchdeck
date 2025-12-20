from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class SpeedtestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float


class SpeedtestService:
    async def run(self) -> SpeedtestResult:
        return await asyncio.to_thread(self._run_sync)

    def _run_sync(self) -> SpeedtestResult:
        try:
            import speedtest  # type: ignore
        except Exception as exc:  # pragma: no cover - best-effort import
            raise RuntimeError("Install the 'speedtest-cli' package to run speed tests.") from exc

        st = speedtest.Speedtest()
        st.get_best_server()
        down = st.download()
        up = st.upload()
        ping = float(st.results.ping)

        return SpeedtestResult(
            download_mbps=down / 1e6,
            upload_mbps=up / 1e6,
            ping_ms=ping,
        )
