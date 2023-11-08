from __future__ import annotations

import dataclasses
from pathlib import Path


@dataclasses.dataclass(init=False)
class Config:
    token: str
    library_path: Path
    use_checksums: bool
    log_level: str
    dry_run: bool
    compatibility_mode: bool
