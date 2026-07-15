from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any


@dataclasses.dataclass(frozen=True)
class Config:
    token: str
    library_path: Path
    use_checksums: bool = False
    validate: bool = False
    log_level: str = "INFO"
    dry_run: bool = False
    compatibility_mode: bool = False
    omit_publisher: bool = False
    threads: int = 5
    do_check: bool = True
    log_up_to_date: bool = True

    @classmethod
    def from_namespace(cls, namespace: Any) -> Config:
        """Create Config from argparse namespace."""
        return cls(
            token=namespace.token,
            library_path=namespace.library_path,
            use_checksums=namespace.use_checksums,
            validate=namespace.validate,
            log_level=namespace.log_level,
            dry_run=namespace.dry_run,
            compatibility_mode=namespace.compatibility_mode,
            omit_publisher=namespace.omit_publisher,
            threads=namespace.threads,
            do_check=namespace.do_check,
            log_up_to_date=namespace.log_up_to_date,
        )
