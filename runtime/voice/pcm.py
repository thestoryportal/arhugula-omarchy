"""Bounded s16le framing and an uncalibrated energy-only VAD candidate."""
from dataclasses import dataclass
import math
import struct


class PcmFramer:
    """Single-owner parser; malformed streams require a new instance."""

    def __init__(self):
        self._remainder = b""
        self._state = "open"

    def feed(self, chunk: bytes) -> list[bytes]:
        if self._state != "open":
            raise ValueError("PCM stream is closed")
        if type(chunk) is not bytes or len(chunk) > 65536:
            self._remainder = b""
            self._state = "failed"
            raise ValueError("PCM chunk must be bounded immutable bytes")
        combined = self._remainder + chunk
        end = len(combined) // 640 * 640
        self._remainder = combined[end:]
        return [combined[index:index + 640] for index in range(0, end, 640)]

    def finish(self) -> None:
        if self._state == "failed":
            raise ValueError("PCM stream failed")
        if self._remainder:
            self._remainder = b""
            self._state = "failed"
            raise ValueError("PCM stream ends with an incomplete frame")
        self._state = "finished"


@dataclass(frozen=True)
class EnergyVad:
    """Measures amplitude, not speech identity; threshold needs real replay proof."""

    threshold_rms: float

    def __post_init__(self):
        if type(self.threshold_rms) not in (int, float) or not 0 < self.threshold_rms < 1:
            raise ValueError("RMS threshold must be finite and strictly between zero and one")

    def is_speech(self, pcm: bytes) -> bool:
        if type(pcm) is not bytes or len(pcm) != 640:
            raise ValueError("VAD requires one immutable 20 ms s16le frame")
        energy = sum(sample * sample for (sample,) in struct.iter_unpack("<h", pcm))
        rms = math.sqrt(energy / 320) / 32768
        return rms >= self.threshold_rms
