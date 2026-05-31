from fastapi import HTTPException

from app.services.auth import can_access_kb_category, has_permission, authenticate, create_access_token, verify_access_token


def test_demo_auth_login_and_token_verify():
    user = authenticate("manager", "manager123")
    token = create_access_token(user)
    payload = verify_access_token(token)

    assert user["role"] == "manager"
    assert user["role_label"] == "部门负责人"
    assert payload["sub"] == "manager"


def test_demo_auth_rejects_bad_password():
    try:
        authenticate("manager", "wrong")
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("bad password should be rejected")


def test_rbac_permissions_match_demo_roles():
    admin = authenticate("admin", "admin123")
    hr = authenticate("hr", "hr123")
    employee = authenticate("employee", "employee123")

    assert has_permission(admin, "model_config:write")
    assert not has_permission(hr, "model_config:write")
    assert not has_permission(employee, "knowledge_base:delete")
    assert not has_permission(employee, "knowledge_base:read_all")
    assert can_access_kb_category(hr, "policy")
    assert not can_access_kb_category(hr, "business")
    assert can_access_kb_category(employee, "policy")
    assert not can_access_kb_category(employee, "business")
    assert not can_access_kb_category(employee, "general")
