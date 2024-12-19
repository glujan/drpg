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
    def complete(checksums_count=1) -> FileTasksResponse:
        return FileTasksResponse(
            url="https://example.com/file.pdf",
            status="Complete",
        )

    @staticmethod
    def preparing() -> FileTasksResponse:
        return FileTasksResponse(
            url="https://example.com/file.pdf",
            status="Preparing download...",
        )


@dataclasses.dataclass
class FileResponse:  # TODO This probably will transform into DownloadItemFixture
    filename: str
    last_modified: str
    checksums: list[Checksum]
