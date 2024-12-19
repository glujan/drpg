from drpg.types import FileTasksResponse


class FileTaskResponseFixture:
    @staticmethod
    def complete() -> FileTasksResponse:
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
