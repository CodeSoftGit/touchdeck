from __future__ import annotations

from types import SimpleNamespace

from touchdeck.services import stats


class _FakeVMem:
    total = 8 * 1024**3
    available = 2 * 1024**3
    percent = 75.0


class _FakePsutil:
    def __init__(self, cpu_pct: float) -> None:
        self._cpu_pct = cpu_pct

    def cpu_percent(self, interval=None):
        return self._cpu_pct

    def virtual_memory(self):
        return _FakeVMem()


def test_stats_read_without_gpu(monkeypatch) -> None:
    fake_psutil = _FakePsutil(cpu_pct=12.5)
    monkeypatch.setattr(stats, "psutil", fake_psutil)

    svc = stats.StatsService(enable_gpu=False)
    result = svc.read()

    assert result.cpu_percent == 12.5
    assert result.ram_total_gb == _FakeVMem.total / (1024**3)
    assert result.ram_used_gb == (_FakeVMem.total - _FakeVMem.available) / (1024**3)
    assert result.ram_percent == _FakeVMem.percent
    assert result.gpu_percent is None


def test_stats_disables_nvml_on_toggle(monkeypatch) -> None:
    fake_psutil = _FakePsutil(cpu_pct=0.0)
    monkeypatch.setattr(stats, "psutil", fake_psutil)

    svc = stats.StatsService(enable_gpu=False)
    svc._nvml = SimpleNamespace()
    svc._nvml_handle = SimpleNamespace()

    svc.set_gpu_enabled(False)

    assert svc._nvml is None
    assert svc._nvml_handle is None
