from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(slots=True)
class Stats:
    cpu_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    ram_percent: float = 0.0

    gpu_percent: float | None = None
    vram_used_gb: float | None = None
    vram_total_gb: float | None = None
    vram_percent: float | None = None


class StatsService:
    def __init__(self, *, enable_gpu: bool = True) -> None:
        # Prime cpu_percent so first read isn't meaningless
        psutil.cpu_percent(interval=None)
        self._nvml = None
        self._nvml_handle = None
        self._gpu_enabled = enable_gpu
        if self._gpu_enabled:
            self._try_init_nvml()

    def _try_init_nvml(self) -> None:
        try:
            import pynvml  # provided by nvidia-ml-py

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self._nvml = None
            self._nvml_handle = None

    def read(self) -> Stats:
        cpu = float(psutil.cpu_percent(interval=None))
        vm = psutil.virtual_memory()

        ram_total = vm.total / (1024**3)
        ram_used = (vm.total - vm.available) / (1024**3)
        ram_percent = float(vm.percent)

        out = Stats(
            cpu_percent=cpu,
            ram_used_gb=ram_used,
            ram_total_gb=ram_total,
            ram_percent=ram_percent,
        )

        if self._gpu_enabled and self._nvml and self._nvml_handle:
            try:
                util = self._nvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                mem = self._nvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
                out.gpu_percent = float(util.gpu)
                out.vram_used_gb = mem.used / (1024**3)
                out.vram_total_gb = mem.total / (1024**3)
                out.vram_percent = (
                    float(mem.used / mem.total * 100.0) if mem.total else None
                )
            except Exception:
                pass

        return out

    def set_gpu_enabled(self, enabled: bool) -> None:
        self._gpu_enabled = enabled
        if enabled and self._nvml is None:
            self._try_init_nvml()
        if not enabled:
            self._nvml = None
            self._nvml_handle = None
