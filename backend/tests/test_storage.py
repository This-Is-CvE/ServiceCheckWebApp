import pytest

from app import config, storage


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def upload_blob(self, key, data, overwrite=False, content_settings=None):
        self.blobs[key] = data

    def download_blob(self, key):
        data = self.blobs[key]
        return type("D", (), {"readall": lambda self: data})()

    def delete_blob(self, key):
        del self.blobs[key]


@pytest.fixture
def blob(monkeypatch):
    fake = FakeContainer()
    monkeypatch.setattr(config, "STORAGE_BACKEND", "azure")
    monkeypatch.setattr(storage, "_container", lambda: fake)
    return fake


def test_documents_go_to_blob_storage_and_not_into_db(client, auth, blob):
    product = client.get("/api/offers", headers=auth).json()[0]["products"][0]
    cust = client.post("/api/customers", json={"name": "Blob GmbH"}, headers=auth).json()
    ob = client.post("/api/onboardings", json={"customer_id": cust["id"], "product_id": product["id"]}, headers=auth).json()

    filed = client.post(f"/api/onboardings/{ob['id']}/documents", headers=auth).json()
    doc = filed["documents"][0]
    assert len(blob.blobs) == 1
    (key, data), = blob.blobs.items()
    assert key.startswith(f"onboardings/{ob['id']}/") and data.startswith(b"%PDF")

    dl = client.get(f"/api/onboardings/{ob['id']}/documents/{doc['id']}", headers=auth)
    assert dl.content == data

    client.delete(f"/api/onboardings/{ob['id']}/documents/{doc['id']}", headers=auth)
    assert blob.blobs == {}

    client.post(f"/api/onboardings/{ob['id']}/documents", headers=auth)
    assert client.delete(f"/api/onboardings/{ob['id']}", headers=auth).status_code == 204
    assert blob.blobs == {}


def test_documents_filed_in_db_stay_readable_after_switching_backend(client, auth, monkeypatch):
    product = client.get("/api/offers", headers=auth).json()[0]["products"][0]
    cust = client.post("/api/customers", json={"name": "Wechsel GmbH"}, headers=auth).json()
    ob = client.post("/api/onboardings", json={"customer_id": cust["id"], "product_id": product["id"]}, headers=auth).json()
    doc = client.post(f"/api/onboardings/{ob['id']}/documents", headers=auth).json()["documents"][0]  # Backend "db"
    monkeypatch.setattr(config, "STORAGE_BACKEND", "azure")
    assert client.get(f"/api/onboardings/{ob['id']}/documents/{doc['id']}", headers=auth).content.startswith(b"%PDF")
