from typing import TypedDict


class TokenResponse(TypedDict):
    token: str
    refreshToken: str
    refreshTokenTTL: int


class FileTasksResponse(TypedDict):
    file_tasks_id: str
    message: str
    download_url: str
    progress: str  # TODO


class Product(TypedDict):
    productId: str
    publisher: "Publisher"
    name: str
    bundleId: int
    orderProductId: str  # Used to generate download file
    fileLastModified: str
    files: list["DownloadItem"]


class Publisher(TypedDict):
    name: str


class DownloadItem(TypedDict):
    index: int
    filename: str
    orderProductDownloadId: int
    checksums: list["Checksum"]


class Checksum(TypedDict):
    checksum: str
    checksumDate: str
