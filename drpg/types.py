from typing import TypedDict


class TokenResponse(TypedDict):
    token: str
    refreshToken: str
    refreshTokenTTL: int


class FileTasksResponse(TypedDict):
    url: str
    status: str


class Product(TypedDict):
    productId: str
    publisher: "Publisher"
    name: str
    bundleId: int
    orderProductId: int
    fileLastModified: str  # ISO format
    files: list["DownloadItem"]


class Publisher(TypedDict):
    name: str


class DownloadItem(TypedDict):
    index: int
    filename: str
    checksums: list["Checksum"]


class Checksum(TypedDict):
    checksum: str
    checksumDate: str  # ISO format
