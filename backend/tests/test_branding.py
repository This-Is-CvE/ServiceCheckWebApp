import io

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def clean_logos(client, auth):
    """Die Datenbank gilt für die ganze Testsitzung: Logos vor und nach jedem Test zurücksetzen."""
    def reset():
        for kind in ("app", "report"):
            client.delete(f"/api/branding/logo/{kind}", headers=auth)
    reset()
    yield
    reset()


def _image(fmt: str, size=(600, 100), color=(0, 119, 169)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _put(client, auth, content: bytes, kind="app", name="logo.png", mime="image/png"):
    return client.put(f"/api/branding/logo/{kind}", files={"file": (name, content, mime)}, headers=auth)


def _consultant(client, auth):
    client.post("/api/users", json={"username": "carl", "password": "secret123"}, headers=auth)
    tok = client.post("/api/auth/login", data={"username": "carl", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_default_logo_is_public_and_cached_by_etag(client):
    r = client.get("/api/branding/logo/app")  # ohne Anmeldung: die Anmeldeseite braucht es
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG")
    assert r.headers["x-content-type-options"] == "nosniff"
    again = client.get("/api/branding/logo/app", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    assert client.get("/api/branding/logo/unbekannt").status_code == 422


def test_admin_can_replace_and_reset_application_logo(client, auth):
    default = client.get("/api/branding/logo/app")
    state = client.get("/api/branding", headers=auth).json()
    assert state["app"]["custom"] is False and state["report"] == {**state["report"], "custom": False, "inherited": True}

    png = _image("PNG")
    info = _put(client, auth, png).json()["app"]
    assert info["custom"] is True and (info["width"], info["height"]) == (600, 100) and info["updated_by"] == "admin"

    mine = client.get("/api/branding/logo/app")
    assert mine.content == png and mine.headers["etag"] != default.headers["etag"]

    # JPEG ersetzt PNG, es gibt je Verwendungszweck nur ein Logo
    jpg = _image("JPEG", (300, 300))
    assert _put(client, auth, jpg, name="logo.jpg", mime="image/jpeg").status_code == 200
    now = client.get("/api/branding/logo/app")
    assert now.content == jpg and now.headers["content-type"] == "image/jpeg"

    assert client.delete("/api/branding/logo/app", headers=auth).status_code == 204
    assert client.get("/api/branding/logo/app").content == default.content
    assert client.get("/api/branding", headers=auth).json()["app"]["custom"] is False
    assert client.delete("/api/branding/logo/app", headers=auth).status_code == 204  # wiederholbar


def test_report_logo_is_separate_and_falls_back_to_the_application_logo(client, auth):
    default = client.get("/api/branding/logo/app").content
    assert client.get("/api/branding/logo/report").content == default   # nichts hochgeladen: Standardlogo

    app_logo = _image("PNG", (400, 100), (10, 20, 30))
    _put(client, auth, app_logo, "app")
    assert client.get("/api/branding/logo/report").content == app_logo   # folgt dem Anwendungslogo
    assert client.get("/api/branding", headers=auth).json()["report"]["inherited"] is True

    report_logo = _image("JPEG", (500, 200), (200, 0, 0))
    out = _put(client, auth, report_logo, "report", "r.jpg", "image/jpeg").json()
    assert out["report"]["custom"] is True and out["report"]["inherited"] is False
    assert client.get("/api/branding/logo/report").content == report_logo
    assert client.get("/api/branding/logo/app").content == app_logo      # Anwendungslogo bleibt unberührt

    # Report-Logo entfernen: wieder das Anwendungslogo, und das Anwendungslogo bleibt erhalten
    assert client.delete("/api/branding/logo/report", headers=auth).status_code == 204
    assert client.get("/api/branding/logo/report").content == app_logo
    assert client.get("/api/branding/logo/app").content == app_logo

    # Anwendungslogo entfernen: das Report-Logo bleibt, wenn es eigenes ist
    _put(client, auth, report_logo, "report", "r.jpg", "image/jpeg")
    client.delete("/api/branding/logo/app", headers=auth)
    assert client.get("/api/branding/logo/app").content == default
    assert client.get("/api/branding/logo/report").content == report_logo


def test_only_admins_can_change_logos(client, auth):
    h = _consultant(client, auth)
    for kind in ("app", "report"):
        assert _put(client, h, _image("PNG"), kind).status_code == 403
        assert client.delete(f"/api/branding/logo/{kind}", headers=h).status_code == 403
    assert client.get("/api/branding", headers=h).status_code == 403
    assert client.put("/api/branding/logo/app", files={"file": ("l.png", _image("PNG"), "image/png")}).status_code == 401


def test_invalid_logo_files_are_rejected(client, auth):
    before = client.get("/api/branding/logo/app").content

    for kind in ("app", "report"):
        # Dateiendung und Content-Type sind egal, der Inhalt entscheidet
        assert _put(client, auth, b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", kind).status_code == 400
        assert _put(client, auth, b"das ist kein Bild", kind).status_code == 400
        assert _put(client, auth, b"", kind).status_code == 400
        assert _put(client, auth, _image("GIF"), kind, "logo.gif", "image/gif").status_code == 400
        assert _put(client, auth, _image("PNG", (5000, 50)), kind).status_code == 400   # zu breit
        assert _put(client, auth, _image("PNG", (8, 8)), kind).status_code == 400       # zu klein
        assert _put(client, auth, _image("PNG")[:200], kind).status_code == 400          # abgeschnitten
        assert _put(client, auth, b"\x89PNG\r\n\x1a\n" + b"0" * 1_000_001, kind).status_code == 413

    assert client.get("/api/branding/logo/app").content == before  # nichts davon hat ein Logo verändert
    assert client.get("/api/branding", headers=auth).json()["report"]["custom"] is False


def test_pdfs_use_the_report_logo_not_the_application_logo(client, auth):
    product = client.get("/api/offers", headers=auth).json()[0]["products"][0]
    cust = client.post("/api/customers", json={"name": "Logo AG"}, headers=auth).json()
    check = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": product["id"]}, headers=auth).json()

    def pdf():
        r = client.get(f"/api/checks/{check['id']}/report.pdf", headers=auth)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        return r.content

    def images(content: bytes) -> bytes:
        # Das eingebettete Logo ändert die Bildobjekte, nicht den Seitentext: PDF-Größe als einfacher Indikator
        return str(len(content)).encode()

    standard = pdf()
    # Nur das Anwendungslogo ändern: Ohne eigenes Report-Logo folgt das PDF ihm
    _put(client, auth, _image("PNG", (900, 300), (200, 0, 0)), "app")
    follows_app = pdf()
    assert images(follows_app) != images(standard)

    # Eigenes Report-Logo: das PDF nutzt jetzt dieses, und eine Änderung des Anwendungslogos wirkt nicht mehr
    _put(client, auth, _image("JPEG", (1200, 100), (0, 100, 0)), "report", "r.jpg", "image/jpeg")   # sehr breit
    with_report = pdf()
    assert images(with_report) != images(follows_app)
    _put(client, auth, _image("PNG", (100, 900), (0, 0, 200)), "app")                                # hochkant
    assert len(pdf()) == len(with_report)

    assert client.delete("/api/branding/logo/report", headers=auth).status_code == 204
    assert pdf().startswith(b"%PDF")
