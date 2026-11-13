"""The decision log: one JSON line per decision, with a short reason code. We debug with it and show it to the jury."""
from __future__ import annotations

import json
from typing import IO, Optional


class DecLog:
    def __init__(self, path: Optional[str] = None):
        self._file: Optional[IO[str]] = open(path, "a", encoding="utf-8") if path else None
        self.counts: dict[str, int] = {}

    def __call__(self, at: int, code: str, ref: str = "", **info: object) -> None:
        self.counts[code] = self.counts.get(code, 0) + 1
        if self._file:
            self._file.write(json.dumps({"at": at, "code": code, "ref": ref, **info}, separators=(",", ":")) + "\n")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
