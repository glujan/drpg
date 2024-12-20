from drpg.types import PrepareDownloadUrlResponse


class PrepareDownloadUrlResponseFixture:
    @staticmethod
    def complete() -> PrepareDownloadUrlResponse:
        return PrepareDownloadUrlResponse(
            url="https://example.com/file.pdf",
            status="Complete",
        )

    @staticmethod
    def preparing() -> PrepareDownloadUrlResponse:
        return PrepareDownloadUrlResponse(
            url="https://example.com/file.pdf",
            status="Preparing download...",
        )
