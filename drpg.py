from cgi import parse_header
from contextlib import closing
from datetime import datetime, timedelta
from functools import partial
from hashlib import md5
from os import environ
from pathlib import Path
from time import sleep, timezone

from httpx import Client as HttpClient, StatusCode


client = HttpClient(base_url="https://www.drivethrurpg.com")


def login(token):
    resp = client.post(
        "/api/v1/token",
        params={"fields": "first_name,last_name,customers_id"},
        headers={"Authorization": f"Bearer {token}"},
    )

    if resp.status_code == StatusCode.UNAUTHORIZED:
        raise AttributeError("Provided token is invalid")
    return resp.json()["message"]


def get_products(customer_id, access_token, per_page=100):
    """
    resp_pagination_ends = {"status": "success", "message": []}
    """

    # URL from app with more params:
    #  "fields": "products_name,cover_url,date_purchased,products_filesize,publishers_name,products_thumbnail100",
    #  "embed": "files.filename,files.last_modified,files.checksums,files.raw_filesize,filters.filters_name,filters.filters_id,filters.parent_id",

    get_product_page = partial(
        client.get,
        f"/api/v1/customers/{customer_id}/products",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )
    page = 1

    while result := _get_products_page(get_product_page, page, per_page):
        yield from result
        page += 1


def _get_products_page(func, page, per_page):
    return func(
        params={
            "page": page,
            "per_page": per_page,
            "include_archived": 0,
            "fields": "products_name",
            "embed": "files.filename,files.last_modified,files.checksums",
        }
    ).json()["message"]


def need_download(product, item):
    path = get_file_path(product, item)

    if not path.exists():
        return True

    remote_time = datetime.fromisoformat(item["last_modified"]).utctimetuple()
    local_time = (
        datetime.fromtimestamp(path.stat().st_mtime) + timedelta(seconds=timezone)
    ).utctimetuple()
    if remote_time > local_time:
        return True

    if checksum := get_newest_checksum(item):
        with open(path, "rb") as f:
            if md5(f.read()).hexdigest() != checksum:
                return True

    return False


def get_download_url(product_id, item_id, access_token):
    resp = client.post(
        "/api/v1/file_tasks",
        params={"fields": "download_url,progress"},
        data={"products_id": product_id, "bundle_id": item_id},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {access_token}",
        },
    )

    while (data := resp.json()["message"])["progress"].startswith("Preparing download"):
        sleep(3)
        task_id = data["file_tasks_id"]
        resp = client.get(
            f"/api/v1/file_tasks/{task_id}",
            params={"fields": "download_url,progress,checksums"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    return data


def get_file(url):
    resp = client.get(url)
    content_disposition = resp.headers.get("content-disposition")
    _, val = parse_header(content_disposition)
    return val["filename"], resp.content


def get_file_path(product, item):
    return Path("repository") / product["products_name"] / item["filename"]


def get_newest_checksum(item):
    return max(
        item["checksums"],
        default={"checksum": None},
        key=lambda s: datetime.strptime(s["checksum_date"], "%Y-%m-%d %H:%M:%S"),
    )["checksum"]


def save_item(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as ff:
        ff.write(content)


def sync():
    login_data = login(environ["DRPG_TOKEN"])
    products = get_products(
        login_data["customers_id"], login_data["access_token"], per_page=100
    )
    items = (
        (product, item)
        for product in products
        for item in product.pop("files")
        if need_download(product, item)
    )

    for product, item in items:
        link = get_download_url(
            product["products_id"], item["bundle_id"], login_data["access_token"]
        )["download_url"]
        name, content = get_file(link)
        save_item(get_file_path(product, item), content)


if __name__ == "__main__":
    with closing(client):
        sync()
