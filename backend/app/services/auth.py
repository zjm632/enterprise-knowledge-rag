import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


ADMIN_ROLE = "admin"
MANAGER_ROLE = "manager"
HR_ROLE = "hr"
EMPLOYEE_ROLE = "employee"

ROLE_SCOPES = {
    "admin": ("管理员", "全部知识库、模型设置、操作日志"),
    "manager": ("部门负责人", "部门制度、报销、转正、审批流程"),
    "hr": ("HR", "制度类知识库、考勤、报销、通用流程"),
    "employee": ("普通员工", "公开制度、考勤、报销、通用流程"),
}

ROLE_PERMISSIONS = {
    ADMIN_ROLE: {
        "knowledge_base:create",
        "knowledge_base:delete",
        "knowledge_base:read_all",
        "document:write",
        "qa:ask",
        "logs:read",
        "model_config:read",
        "model_config:write",
        "eval:read",
    },
    MANAGER_ROLE: {
        "knowledge_base:create",
        "knowledge_base:delete",
        "knowledge_base:read_all",
        "document:write",
        "qa:ask",
        "logs:read",
        "model_config:read",
        "eval:read",
    },
    HR_ROLE: {
        "knowledge_base:read_policy",
        "document:write",
        "qa:ask",
        "logs:read",
        "model_config:read",
        "eval:read",
    },
    EMPLOYEE_ROLE: {
        "knowledge_base:read_policy",
        "qa:ask",
        "logs:read",
        "model_config:read",
        "eval:read",
    },
}

POLICY_KB_CATEGORY = "policy"

KB_CATEGORY_LABELS = {
    POLICY_KB_CATEGORY: "制度类",
    "business": "业务类",
    "general": "通用类",
}


@dataclass(frozen=True)
class DemoUser:
    username: str
    password: str
    name: str
    role: str
    avatar: str = ""


DEMO_USERS = {
    "admin": DemoUser("admin", "admin123", "张伟", "admin"),
    "manager": DemoUser("manager", "manager123", "李娜", "manager"),
    "hr": DemoUser("hr", "hr123", "王敏", "hr"),
    "employee": DemoUser("employee", "employee123", "赵强", "employee"),
}


def authenticate(username: str, password: str) -> dict:
    user = DEMO_USERS.get(username.strip().lower())
    if not user or not hmac.compare_digest(user.password, password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
    return user_to_dict(user)


def create_access_token(user: dict) -> str:
    settings = get_settings()
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "exp": int(time.time()) + settings.auth_token_ttl_minutes * 60,
    }
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = _sign(body, settings.auth_secret_key)
    return f"{body}.{signature}"


def current_user_from_request(request: Request) -> dict:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    payload = verify_access_token(token)
    user = DEMO_USERS.get(str(payload.get("sub", "")))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user_to_dict(user, role_override=str(payload.get("role") or user.role))


def has_permission(user: dict, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(str(user.get("role")), set())


def require_permission(user: dict, permission: str) -> None:
    if not has_permission(user, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")


def can_access_kb_category(user: dict, category: str) -> bool:
    role = str(user.get("role"))
    if has_permission(user, "knowledge_base:read_all"):
        return True
    if role in {HR_ROLE, EMPLOYEE_ROLE}:
        return category == POLICY_KB_CATEGORY
    return False


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        body, signature = token.rsplit(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    expected = _sign(body, settings.auth_secret_key)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token signature")
    try:
        payload = json.loads(base64.urlsafe_b64decode(_pad(body)).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token payload") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    return payload


def user_to_dict(user: DemoUser, role_override: str | None = None) -> dict:
    role = role_override or user.role
    role_label, access_scope = ROLE_SCOPES.get(role, ROLE_SCOPES["employee"])
    return {
        "username": user.username,
        "name": user.name,
        "role": role,
        "role_label": role_label,
        "access_scope": access_scope,
        "avatar": user.avatar,
    }


def _sign(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return _b64(digest)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _pad(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")
