from typing import TypedDict


class TokenResponse(TypedDict):
    token: str
    refreshToken: str
    refreshTokenTTL: int


class FileTasksResponse(TypedDict):  # TODO Check schema
    file_tasks_id: str
    download_url: str
    progress: str
    checksums: list["Checksum"]


class Product(TypedDict):
    productId: str
    publisher: "Publisher"
    name: str
    bundleId: int
    orderProductId: str  # Used to generate download file
    fileLastModified: str  # TODO Check format
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
