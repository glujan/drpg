import dataclasses
from datetime import datetime
from random import randint
from typing import Optional

import drpg
import drpg.api
import drpg.cmd
import drpg.sync
from drpg.types import Checksum


def _checksum_date_now():
    return datetime.now().strftime(drpg.sync._checksum_time_format)


def _random_id():
    return str(randint(100, 1000))


@dataclasses.dataclass
class FileTaskResponse:
    file_tasks_id: int
    download_url: Optional[str]
    progress: Optional[str]
    checksums: list[Checksum]

    @classmethod
    def complete(cls, file_task_id, checksums_count=1):
        instance = cls(
            file_task_id,
            "https://example.com/file.pdf",
            "Complete",
            [
                Checksum(checksum="md5hash", checksumDate=_checksum_date_now())
                for _ in range(checksums_count)
            ],
        )
        return dataclasses.asdict(instance)

    @classmethod
    def preparing(cls, file_task_id):
        instance = cls(file_task_id, "https://example.com/file.pdf", "Preparing download...", [])
        return dataclasses.asdict(instance)


@dataclasses.dataclass
class FileResponse:
    filename: str
    last_modified: str
    checksums: list[Checksum]
    bundle_id: str = dataclasses.field(default_factory=_random_id)
