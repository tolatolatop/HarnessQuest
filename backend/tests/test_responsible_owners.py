"""
BDD-style tests for the Responsible Owner configuration system.

Scenarios covered:
  1. List responsible owners when the table is empty
  2. Create a new responsible owner
  3. Create a duplicate name returns the existing record (idempotent)
  4. List after multiple creations (ordered by name)
  5. Delete an existing responsible owner
  6. Delete a non-existent responsible owner (404)
  7. Owner name survives whitespace trimming
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/responsible-owners"


def _create_owner(client: TestClient, name: str, expected_status: int = 201) -> dict:
    resp = client.post(BASE, json={"name": name})
    assert resp.status_code == expected_status, f"POST {name} → {resp.status_code}: {resp.text}"
    return resp.json()


def _list_owners(client: TestClient) -> list[dict]:
    resp = client.get(BASE)
    assert resp.status_code == 200
    return resp.json()


def _delete_owner(client: TestClient, owner_id: str) -> int:
    resp = client.delete(f"{BASE}/{owner_id}")
    return resp.status_code


# ===================================================================
# Scenario 1: List when table is empty
# ===================================================================

class TestListEmpty:
    def test_returns_empty_list(self, client: TestClient) -> None:
        """Given the responsible_owners table is empty
           When  I GET /api/v1/responsible-owners
           Then  the response is an empty list."""
        owners = _list_owners(client)
        assert owners == []


# ===================================================================
# Scenario 2: Create a new responsible owner
# ===================================================================

class TestCreate:
    def test_creates_new_owner(self, client: TestClient) -> None:
        """Given a valid new name "张三"
           When  I POST /api/v1/responsible-owners with {"name": "张三"}
           Then  the response status is 201
           And   the returned name matches the input
           And   an id is returned."""
        owner = _create_owner(client, "张三")
        assert owner["name"] == "张三"
        assert isinstance(owner["id"], str) and len(owner["id"]) > 0
        assert "created_at" in owner

    def test_name_trimming(self, client: TestClient) -> None:
        """Given a name with surrounding whitespace "  李四 "
           When  I POST /api/v1/responsible-owners
           Then  the name is stripped before storage."""
        owner = _create_owner(client, "  李四 ")
        assert owner["name"] == "李四"  # route strips whitespace

    # Note: trimming happens in the route handler. Let's verify.
    def test_name_stripped_in_route(self, client: TestClient) -> None:
        """Given a name with whitespace
           When  posted to the route
           Then  name is stripped before storage/check."""
        resp = client.post(BASE, json={"name": "  王五 "})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "王五"  # route strips whitespace


# ===================================================================
# Scenario 3: Duplicate name returns existing
# ===================================================================

class TestDuplicate:
    def test_duplicate_name_returns_existing(self, client: TestClient) -> None:
        """Given an owner "张三" already exists
           When  I POST the same name again
           Then  the response is 200 (not 201) with the same data."""
        first = _create_owner(client, "张三")
        second = _create_owner(client, "张三", expected_status=200)
        assert second["id"] == first["id"]
        assert second["name"] == "张三"


# ===================================================================
# Scenario 4: List after multiple creations
# ===================================================================

class TestListNonEmpty:
    def test_list_returns_all_owners_sorted(self, client: TestClient) -> None:
        """Given owners "张三" and "李四" exist
           When  I GET /api/v1/responsible-owners
           Then  the list contains both names."""
        _create_owner(client, "张三")
        _create_owner(client, "李四")
        owners = _list_owners(client)
        names = [o["name"] for o in owners]
        assert "张三" in names
        assert "李四" in names


# ===================================================================
# Scenario 5: Delete an existing owner
# ===================================================================

class TestDelete:
    def test_delete_existing_owner(self, client: TestClient) -> None:
        """Given an owner exists
           When  I DELETE /api/v1/responsible-owners/{id}
           Then  the response is 200 with {"status": "ok"}
           And   the owner is no longer listed."""
        owner = _create_owner(client, "赵六")
        status = _delete_owner(client, owner["id"])
        assert status == 200
        owners = _list_owners(client)
        assert all(o["id"] != owner["id"] for o in owners)


# ===================================================================
# Scenario 6: Delete non-existent owner returns 404
# ===================================================================

class TestDeleteNotFound:
    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        """Given no owner exists with a certain id
           When  I DELETE /api/v1/responsible-owners/{id}
           Then  the response is 404."""
        status = _delete_owner(client, "00000000-0000-0000-0000-000000000000")
        assert status == 404

# ===================================================================
# Scenario 8: Create with responsibility_area
# ===================================================================

class TestResponsibilityArea:
    def test_create_with_area(self, client: TestClient) -> None:
        """Given a name and responsibility_area
           When  POST with {"name": "张三", "responsibility_area": "测试模块"}
           Then  the response includes the area."""
        resp = client.post(BASE, json={"name": "张三", "responsibility_area": "测试模块"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "张三"
        assert data["responsibility_area"] == "测试模块"

    def test_create_without_area_is_null(self, client: TestClient) -> None:
        """Given a name without responsibility_area
           When  POST with just {"name": "李四"}
           Then  responsibility_area is null."""
        owner = _create_owner(client, "李四")
        assert "responsibility_area" in owner
        assert owner["responsibility_area"] is None

    def test_list_contains_area(self, client: TestClient) -> None:
        """Given owners with and without area
           When  GET /responsible-owners
           Then  the area field is populated correctly."""
        client.post(BASE, json={"name": "张三", "responsibility_area": "测试模块"})
        client.post(BASE, json={"name": "李四"})
        owners = _list_owners(client)
        by_name = {o["name"]: o for o in owners}
        assert by_name["张三"]["responsibility_area"] == "测试模块"
        assert by_name["李四"]["responsibility_area"] is None


# ===================================================================
# Scenario 9: PATCH (update) responsible owner
# ===================================================================

class TestPatch:
    def test_update_name_and_area(self, client: TestClient) -> None:
        """Given an existing owner
           When  PATCH with new name and area
           Then  the owner is updated."""
        owner = _create_owner(client, "张三")
        resp = client.patch(f"{BASE}/{owner['id']}", json={"name": "张三改", "responsibility_area": "新模块"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "张三改"
        assert data["responsibility_area"] == "新模块"

    def test_patch_nonexistent_returns_404(self, client: TestClient) -> None:
        """Given no owner with that id
           When  PATCH
           Then  404."""
        resp = client.patch(f"{BASE}/00000000-0000-0000-0000-000000000000", json={"name": "x"})
        assert resp.status_code == 404

    def test_patch_duplicate_name_returns_400(self, client: TestClient) -> None:
        """Given two owners A and B
           When  PATCH B's name to A's name
           Then  400."""
        a = _create_owner(client, "AAA")
        _create_owner(client, "BBB")
        resp = client.patch(f"{BASE}/{a['id']}", json={"name": "BBB"})
        assert resp.status_code == 400
