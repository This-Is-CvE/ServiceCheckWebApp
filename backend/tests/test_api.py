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
    product = client.get("/api/offers", headers=auth).json()[0]["products"][0]
    cust = client.post("/api/customers", json={"name": "Onboard KG"}, headers=auth).json()
    ob = client.post("/api/onboardings", json={"customer_id": cust["id"], "product_id": product["id"]},
                     headers=auth).json()
    assert ob["open_required"] and ob["progress"] == 0

    assert client.post(f"/api/onboardings/{ob['id']}/complete", headers=auth).status_code == 422

    ob = client.post(f"/api/onboardings/{ob['id']}/assets",
                     json={"category": "Host", "name": "Dell R750", "model": "R750", "serial_number": "ABC123",
                           "quantity": 1}, headers=auth).json()
    assert ob["assets"][0]["serial_number"] == "ABC123" and ob["assets"][0]["model"] == "R750"
    assert "Mindestens ein Ansprechpartner" in ob["open_required"]
    ob = client.post(f"/api/onboardings/{ob['id']}/contacts",
                     json={"name": "Erika Muster", "role": "IT-Leitung", "phone": "040 1", "email": "e@x.de"},
                     headers=auth).json()
    assert ob["contacts"][0]["role"] == "IT-Leitung" and "Mindestens ein Ansprechpartner" not in ob["open_required"]

    for it in ob["items"]:
        body = {"value": "ok"} if it["section"] == "general" else {"done": True}
        r = client.put(f"/api/onboardings/{ob['id']}/items/{it['id']}", json=body, headers=auth)
        assert r.status_code == 200
    ob = r.json()
    assert ob["open_required"] == [] and ob["progress"] == 100
    done = client.post(f"/api/onboardings/{ob['id']}/complete", headers=auth).json()
    assert done["status"] == "completed"


def test_onboarding_documents_are_filed(client, auth):
    product = client.get("/api/offers", headers=auth).json()[0]["products"][0]
    cust = client.post("/api/customers", json={"name": "Ablage GmbH", "contact_name": "Frau Ü"}, headers=auth).json()
    ob = client.post("/api/onboardings", json={"customer_id": cust["id"], "product_id": product["id"]},
                     headers=auth).json()
    client.post(f"/api/onboardings/{ob['id']}/contacts", json={"name": "Max Muster"}, headers=auth)
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


def test_new_product_gets_default_onboarding_template(client, auth):
    offer = client.post("/api/offers", json={"name": "Managed Firewall"}, headers=auth).json()
    prod = client.post(f"/api/offers/{offer['id']}/products", json={"name": "FortiGate"}, headers=auth).json()
    tpl = client.get(f"/api/products/{prod['id']}/template", headers=auth).json()
    assert {i["section"] for i in tpl} == {"general", "checklist", "readiness"}
    assert all(i["extension_id"] is None for i in tpl)


def _product(client, auth, name_part):
    for o in client.get("/api/offers", headers=auth).json():
        for p in o["products"]:
            if name_part in p["name"]:
                return p
    raise AssertionError(name_part)


def test_extensions_are_only_checked_when_selected(client, auth):
    vsphere = _product(client, auth, "vSphere")
    assert [e["name"] for e in vsphere["extensions"]] == ["VMware vSAN"]
    vsan = vsphere["extensions"][0]
    assert vsphere["parameter_count"] > 10 and vsan["parameter_count"] == 3

    cust = client.post("/api/customers", json={"name": "Ext AG", "kt_number": "KT-4711"}, headers=auth).json()
    assert cust["kt_number"] == "KT-4711"
    plain = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": vsphere["id"]}, headers=auth).json()
    with_ext = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": vsphere["id"],
                                                "extension_ids": [vsan["id"]]}, headers=auth).json()
    assert len(with_ext["items"]) == len(plain["items"]) + 3
    assert with_ext["extensions"] == [{"id": vsan["id"], "name": "VMware vSAN"}]
    assert {i["extension_name"] for i in with_ext["items"]} == {None, "VMware vSAN"}
    assert any(i["section"].startswith("VMware vSAN ›") for i in with_ext["items"])
    assert plain["customer_kt_number"] == "KT-4711"

    # Erweiterung nachträglich abwählen: Antworten des Basiskatalogs bleiben
    base_item = next(i for i in with_ext["items"] if i["extension_name"] is None)
    client.put(f"/api/checks/{with_ext['id']}/items/{base_item['id']}", json={"answer": "yes"}, headers=auth)
    back = client.put(f"/api/checks/{with_ext['id']}/extensions", json={"extension_ids": []}, headers=auth).json()
    assert len(back["items"]) == len(plain["items"]) and back["extensions"] == []
    assert next(i for i in back["items"] if i["id"] == base_item["id"])["answer"] == "yes"
    again = client.put(f"/api/checks/{with_ext['id']}/extensions", json={"extension_ids": [vsan["id"]]},
                       headers=auth).json()
    assert len(again["items"]) == len(plain["items"]) + 3

    # fremde Erweiterung wird abgelehnt
    s2d = _product(client, auth, "Hyper-V")["extensions"][0]
    r = client.post("/api/checks", json={"customer_id": cust["id"], "product_id": vsphere["id"],
                                         "extension_ids": [s2d["id"]]}, headers=auth)
    assert r.status_code == 422


def test_onboarding_template_per_product_and_extension(client, auth):
    hv = _product(client, auth, "Hyper-V")
    cust = client.post("/api/customers", json={"name": "Vorlage GmbH"}, headers=auth).json()
    base = client.post("/api/onboardings", json={"customer_id": cust["id"], "product_id": hv["id"]}, headers=auth).json()
    ext_ids = [e["id"] for e in hv["extensions"]]
    full = client.post("/api/onboardings", json={"customer_id": cust["id"], "product_id": hv["id"],
                                                 "extension_ids": ext_ids}, headers=auth).json()
    assert len(full["items"]) > len(base["items"]) and len(full["extensions"]) == 2
    assert {i["extension_name"] for i in full["items"]} >= {"Storage Spaces Direct (S2D)", "Azure Local"}
    assert full["product_name"] == "Microsoft Hyper-V"
    # Änderung der Auswahl
    smaller = client.put(f"/api/onboardings/{full['id']}/extensions", json={"extension_ids": []}, headers=auth).json()
    assert len(smaller["items"]) == len(base["items"])
    # Vorlagenpunkt einer Erweiterung anlegen
    item = client.post(f"/api/products/{hv['id']}/template",
                       json={"section": "checklist", "label": "Extra", "extension_id": ext_ids[0]}, headers=auth)
    assert item.status_code == 201 and item.json()["extension_id"] == ext_ids[0]


def test_extension_and_parameter_management(client, auth):
    offer = client.post("/api/offers", json={"name": "Managed Network"}, headers=auth).json()
    prod = client.post(f"/api/offers/{offer['id']}/products", json={"name": "Cisco"}, headers=auth).json()
    ext = client.post(f"/api/products/{prod['id']}/extensions", json={"name": "SD-WAN"}, headers=auth).json()
    p = client.post(f"/api/products/{prod['id']}/parameters",
                    json={"name": "Controller erreichbar", "weight": 7, "extension_id": ext["id"]}, headers=auth)
    assert p.status_code == 201 and p.json()["extension_id"] == ext["id"]
    got = client.get(f"/api/products/{prod['id']}", headers=auth).json()
    assert got["parameter_count"] == 0 and got["extensions"][0]["parameter_count"] == 1
    assert client.delete(f"/api/extensions/{ext['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/products/{prod['id']}/parameters", headers=auth).json() == []
    assert client.delete(f"/api/offers/{offer['id']}", headers=auth).status_code == 204
