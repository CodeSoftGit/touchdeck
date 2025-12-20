from __future__ import annotations

from dataclasses import dataclass

from touchdeck import utils


def test_clamp_bounds() -> None:
    assert utils.clamp(5, 0, 10) == 5
    assert utils.clamp(-1, 0, 10) == 0
    assert utils.clamp(11, 0, 10) == 10


def test_ms_to_mmss_formats_and_guards_negative() -> None:
    assert utils.ms_to_mmss(0) == "0:00"
    assert utils.ms_to_mmss(1000) == "0:01"
    assert utils.ms_to_mmss(61_000) == "1:01"
    assert utils.ms_to_mmss(-5) == "0:00"


def test_first_str_handles_variants_and_sequences() -> None:
    @dataclass
    class Variant:
        value: str

    assert utils.first_str(None) == ""
    assert utils.first_str(["hello", "world"]) == "hello"
    assert utils.first_str(("a", "b")) == "a"
    assert utils.first_str(Variant("wrapped")) == "wrapped"

