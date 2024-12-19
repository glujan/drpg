import dataclasses
from datetime import datetime

import drpg
import drpg.api
import drpg.cmd
import drpg.sync
from drpg.types import Checksum, FileTasksResponse


def _checksum_date_now():
    return datetime.now().strftime(drpg.sync._checksum_time_format)


class FileTaskResponseFixture:
    @staticmethod
    def complete(file_task_id, checksums_count=1) -> FileTasksResponse:
        return FileTasksResponse(
            file_tasks_id=file_task_id,
            download_url="https://example.com/file.pdf",
            progress="Complete",
            checksums=[
                Checksum(checksum="md5hash", checksumDate=_checksum_date_now())
                for _ in range(checksums_count)
            ],
        )

    @staticmethod
    def preparing(file_task_id) -> FileTasksResponse:
        return FileTasksResponse(
            file_tasks_id=file_task_id,
            download_url="https://example.com/file.pdf",
            progress="Preparing download...",
            checksums=[],
        )


@dataclasses.dataclass
class FileResponse:  # TODO This probably will transform into DownloadItemFixture
    filename: str
    last_modified: str
    checksums: list[Checksum]
