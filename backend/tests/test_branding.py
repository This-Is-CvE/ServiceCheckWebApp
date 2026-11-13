import io

from PIL import Image


def _image(fmt: str, size=(600, 100), color=(0, 119, 169)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _put(client, auth, content: bytes, name="logo.png", mime="image/png"):
    return client.put("/api/branding/logo", files={"file": (name, content, mime)}, headers=auth)


def _consultant(client, auth):
    client.post("/api/users", json={"username": "carl", "password": "secret123"}, headers=auth)
    tok = client.post("/api/auth/login", data={"username": "carl", "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_default_logo_is_public_and_cached_by_etag(client):
    r = client.get("/api/branding/logo")  # ohne Anmeldung: die Anmeldeseite braucht es
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG")
    assert r.headers["x-content-type-options"] == "nosniff"
    again = client.get("/api/branding/logo", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


def test_admin_can_replace_and_reset_logo(client, auth):
    default = client.get("/api/branding/logo")
    assert client.get("/api/branding", headers=auth).json()["custom"] is False

    png = _image("PNG")
    info = _put(client, auth, png)
    assert info.status_code == 200
    assert info.json()["custom"] is True and (info.json()["width"], info.json()["height"]) == (600, 100)
    assert info.json()["updated_by"] == "admin"

    mine = client.get("/api/branding/logo")
    assert mine.content == png and mine.headers["etag"] != default.headers["etag"]

    # JPEG ersetzt PNG, es gibt immer nur ein Logo
    jpg = _image("JPEG", (300, 300))
    assert _put(client, auth, jpg, "logo.jpg", "image/jpeg").status_code == 200
    now = client.get("/api/branding/logo")
    assert now.content == jpg and now.headers["content-type"] == "image/jpeg"

    assert client.delete("/api/branding/logo", headers=auth).status_code == 204
    assert client.get("/api/branding/logo").content == default.content
    assert client.get("/api/branding", headers=auth).json()["custom"] is False
    assert client.delete("/api/branding/logo", headers=auth).status_code == 204  # wiederholbar


def test_only_admins_can_change_the_logo(client, auth):
    h = _consultant(client, auth)
    assert _put(client, h, _image("PNG")).status_code == 403
    assert client.delete("/api/branding/logo", headers=h).status_code == 403
    assert client.get("/api/branding", headers=h).status_code == 403
    assert client.put("/api/branding/logo", files={"file": ("l.png", _image("PNG"), "image/png")}).status_code == 401


def test_invalid_logo_files_are_rejected(client, auth):
    before = client.get("/api/branding/logo").content

    # Dateiendung und Content-Type sind egal, der Inhalt entscheidet
    assert _put(client, auth, b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
                "logo.png", "image/png").status_code == 400
    assert _put(client, auth, b"das ist kein Bild", "logo.png").status_code == 400
    assert _put(client, auth, b"").status_code == 400
    assert _put(client, auth, _image("GIF"), "logo.gif", "image/gif").status_code == 400
    assert _put(client, auth, _image("PNG", (5000, 50))).status_code == 400   # zu breit
    assert _put(client, auth, _image("PNG", (8, 8))).status_code == 400       # zu klein
    assert _put(client, auth, _image("PNG")[:200]).status_code == 400          # abgeschnitten
    big = _put(client, auth, b"\x89PNG\r\n\x1a\n" + b"0" * 1_000_001)
    assert big.status_code == 413

    assert client.get("/api/branding/logo").content == before  # nichts davon hat das Logo verändert


def test_pdfs_use_the_custom_logo(client, auth):
    product = client.get("/api/offers", headers=auth).json()[0]["products"][0]
    cust = client.post("/api/customers", json={"name": "Logo AG"}, headers=auth).json()
    check = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": product["id"]}, headers=auth).json()

    def pdf():
        r = client.get(f"/api/checks/{check['id']}/report.pdf", headers=auth)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        return r.content

    standard = pdf()
    assert _put(client, auth, _image("PNG", (1200, 100))).status_code == 200   # sehr breit: wird begrenzt
    wide = pdf()
    assert _put(client, auth, _image("JPEG", (200, 400))).status_code == 200   # hochkant
    tall = pdf()
    assert len({len(standard), len(wide), len(tall)}) > 1 or standard != wide  # Logo wirkt sich auf das PDF aus
    assert client.delete("/api/branding/logo", headers=auth).status_code == 204
    assert pdf().startswith(b"%PDF")
