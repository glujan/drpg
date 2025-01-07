from drpg.types import DownloadUrlResponse


class DownloadUrlResponseFixture:
    @staticmethod
    def complete() -> DownloadUrlResponse:
        return DownloadUrlResponse(
            url="https://example.com/file.pdf",
            status="Complete",
            filename="test.pdf",
            lastChecksum="764efa883dda1e11db47671c4a3bbd9e",
        )

    @staticmethod
    def preparing() -> DownloadUrlResponse:
        return DownloadUrlResponse(
            url="https://example.com/file.pdf",
            status="Preparing download...",
            filename="test.pdf",
            lastChecksum="764efa883dda1e11db47671c4a3bbd9e",
        )
