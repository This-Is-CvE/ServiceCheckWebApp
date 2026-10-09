def test_requires_login(client):
    assert client.get("/api/offers").status_code == 401


def test_bad_login(client):
    assert client.post("/api/auth/login", data={"username": "admin", "password": "nope"}).status_code == 401


def test_service_check_flow_and_pdf(client, auth):
    offers = client.get("/api/offers", headers=auth).json()
    product = offers[0]["products"][0]
    assert product["parameter_count"] > 10

    cust = client.post("/api/customers", json={"name": "Muster GmbH"}, headers=auth).json()
    check = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": product["id"]},
                        headers=auth).json()
    assert check["result"]["light"] == "grey" and len(check["items"]) == product["parameter_count"]

    # unvollständig darf nicht abgeschlossen werden
    assert client.post(f"/api/checks/{check['id']}/complete", headers=auth).status_code == 422

    for it in check["items"]:
        r = client.put(f"/api/checks/{check['id']}/items/{it['id']}",
                       json={"answer": "yes" if not it["is_blocker"] else "no", "comment": "Ü-Test ä"}, headers=auth)
        assert r.status_code == 200
    done = client.post(f"/api/checks/{check['id']}/complete", headers=auth).json()
    assert done["status"] == "completed" and done["result"]["light"] == "red"

    # abgeschlossen = schreibgeschützt
    it = done["items"][0]
    assert client.put(f"/api/checks/{check['id']}/items/{it['id']}", json={"answer": "yes"},
                      headers=auth).status_code == 409

    pdf = client.get(f"/api/checks/{check['id']}/report.pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 3000


def test_catalog_change_does_not_alter_existing_check(client, auth):
    product = client.get("/api/offers", headers=auth).json()[0]["products"][1]
    cust = client.post("/api/customers", json={"name": "Snapshot AG"}, headers=auth).json()
    check = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": product["id"]},
                        headers=auth).json()
    n = len(check["items"])
    params = client.get(f"/api/products/{product['id']}/parameters", headers=auth).json()
    assert client.delete(f"/api/parameters/{params[0]['id']}", headers=auth).status_code == 204
    assert len(client.get(f"/api/checks/{check['id']}", headers=auth).json()["items"]) == n


def test_consultant_cannot_edit_catalog(client, auth):
    client.post("/api/users", json={"username": "bob", "password": "secret123"}, headers=auth)
    tok = client.post("/api/auth/login", data={"username": "bob", "password": "secret123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/offers", json={"name": "X"}, headers=h).status_code == 403
    assert client.get("/api/offers", headers=h).status_code == 200


def test_onboarding_flow(client, auth):
    offer = client.get("/api/offers", headers=auth).json()[0]
    cust = client.post("/api/customers", json={"name": "Onboard KG"}, headers=auth).json()
    ob = client.post("/api/onboardings", json={"customer_id": cust["id"], "offer_id": offer["id"]},
                     headers=auth).json()
    assert ob["open_required"] and ob["progress"] == 0

    assert client.post(f"/api/onboardings/{ob['id']}/complete", headers=auth).status_code == 422

    ob = client.post(f"/api/onboardings/{ob['id']}/assets",
                     json={"category": "Host", "name": "Dell R750", "quantity": 3}, headers=auth).json()
    assert len(ob["assets"]) == 1

    for it in ob["items"]:
        body = {"value": "ok"} if it["section"] == "general" else {"done": True}
        r = client.put(f"/api/onboardings/{ob['id']}/items/{it['id']}", json=body, headers=auth)
        assert r.status_code == 200
    ob = r.json()
    assert ob["open_required"] == [] and ob["progress"] == 100
    done = client.post(f"/api/onboardings/{ob['id']}/complete", headers=auth).json()
    assert done["status"] == "completed"


def test_onboarding_documents_are_filed(client, auth):
    offer = client.get("/api/offers", headers=auth).json()[0]
    cust = client.post("/api/customers", json={"name": "Ablage GmbH", "contact_name": "Frau Ü"}, headers=auth).json()
    ob = client.post("/api/onboardings", json={"customer_id": cust["id"], "offer_id": offer["id"]},
                     headers=auth).json()
    client.post(f"/api/onboardings/{ob['id']}/assets", json={"name": "ESXi 8 Host", "quantity": 2}, headers=auth)

    pdf = client.get(f"/api/onboardings/{ob['id']}/report.pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/onboardings/{ob['id']}", headers=auth).json()["documents"] == []

    filed = client.post(f"/api/onboardings/{ob['id']}/documents", headers=auth).json()
    assert len(filed["documents"]) == 1
    doc = filed["documents"][0]
    dl = client.get(f"/api/onboardings/{ob['id']}/documents/{doc['id']}", headers=auth)
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF") and len(dl.content) == doc["size"]

    # Abschluss legt automatisch ein weiteres Dokument ab
    for it in filed["items"]:
        body = {"value": "ok"} if it["section"] == "general" else {"done": True}
        client.put(f"/api/onboardings/{ob['id']}/items/{it['id']}", json=body, headers=auth)
    done = client.post(f"/api/onboardings/{ob['id']}/complete", headers=auth).json()
    assert len(done["documents"]) == 2


def test_build_own_catalog_from_scratch(client, auth):
    offer = client.post("/api/offers", json={"name": "Managed Backup"}, headers=auth).json()
    prod = client.post(f"/api/offers/{offer['id']}/products", json={"name": "Veeam"}, headers=auth).json()
    p = client.post(f"/api/products/{prod['id']}/parameters",
                    json={"category": "Backup", "name": "Immutable Repository", "weight": 9, "is_blocker": True},
                    headers=auth)
    assert p.status_code == 201
    mine = next(o for o in client.get("/api/offers", headers=auth).json() if o["id"] == offer["id"])
    assert mine["products"][0]["parameter_count"] == 1


def test_new_offer_gets_default_onboarding_template(client, auth):
    offer = client.post("/api/offers", json={"name": "Managed Firewall"}, headers=auth).json()
    tpl = client.get(f"/api/offers/{offer['id']}/template", headers=auth).json()
    assert {i["section"] for i in tpl} == {"general", "checklist", "readiness"}
