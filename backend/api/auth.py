"""
认证 API：用户注册、登录、JWT 鉴权、RBAC 权限控制。

Token 策略：
- Access Token: 30 分钟有效
- Refresh Token: 7 天有效
- 登出时 token 加入内存黑名单
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config.settings import AUTH_CONFIG
from backend.db.session import get_db
from backend.models.user import User


# ---------------------------------------------------------------------------
# 密码 & JWT 工具
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Token 黑名单（登出后失效，进程内内存，重启清空）
_token_blacklist: set[str] = set()


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _check_password_strength(password: str) -> str | None:
    """校验密码强度，返回错误信息或 None。"""
    if len(password) < 8:
        return "密码长度至少 8 位"
    if not re.search(r"[A-Z]", password):
        return "密码需包含至少一个大写字母"
    if not re.search(r"[a-z]", password):
        return "密码需包含至少一个小写字母"
    if not re.search(r"\d", password):
        return "密码需包含至少一个数字"
    return None


def _create_access_token(user_id: int, username: str, role: str) -> str:
    from jose import jwt
    expire = datetime.utcnow() + timedelta(minutes=AUTH_CONFIG["access_token_expire_minutes"])
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, AUTH_CONFIG["secret_key"], algorithm=AUTH_CONFIG["algorithm"])


def _create_refresh_token(user_id: int, username: str) -> str:
    from jose import jwt
    expire = datetime.utcnow() + timedelta(days=AUTH_CONFIG["refresh_token_expire_days"])
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, AUTH_CONFIG["secret_key"], algorithm=AUTH_CONFIG["algorithm"])


def _decode_token(token: str) -> dict:
    from jose import jwt, JWTError
    if token in _token_blacklist:
        raise HTTPException(status_code=401, detail="Token 已失效")
    try:
        return jwt.decode(token, AUTH_CONFIG["secret_key"], algorithms=[AUTH_CONFIG["algorithm"]])
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证凭据")


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserUpdateRole(BaseModel):
    role: str  # user / admin


# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """可选认证：返回当前用户或 None（未登录）。"""
    if credentials is None:
        return None
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "access":
        return None
    user_id = int(payload.get("sub", 0))
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user


async def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str | None:
    """获取当前 Access Token 原文（可选）。"""
    if credentials is None:
        return None
    return credentials.credentials


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """强制认证：必须登录。"""
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或 Token 已过期")
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    """管理员权限：必须是 admin 角色。"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="权限不足，需要管理员权限")
    return user


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户。"""
    # 用户名校验
    if len(data.username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少 2 个字符")

    # 密码强度校验
    err = _check_password_strength(data.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # 唯一性校验
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    if data.email:
        existing_email = db.query(User).filter(User.email == data.email).first()
        if existing_email:
            raise HTTPException(status_code=409, detail="邮箱已被注册")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=_hash_password(data.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=_create_access_token(user.id, user.username, user.role),
        refresh_token=_create_refresh_token(user.id, user.username),
    )


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """用户登录。"""
    user = db.query(User).filter(User.username == data.username, User.is_active == True).first()
    if not user or not _verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return TokenResponse(
        access_token=_create_access_token(user.id, user.username, user.role),
        refresh_token=_create_refresh_token(user.id, user.username),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """用 Refresh Token 换取新的 Access Token。"""
    payload = _decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="需要 Refresh Token")

    user_id = int(payload.get("sub", 0))
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return TokenResponse(
        access_token=_create_access_token(user.id, user.username, user.role),
        refresh_token=_create_refresh_token(user.id, user.username),
    )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user: User = Depends(require_user),
):
    """登出：将当前 Access Token 加入黑名单。"""
    if credentials:
        _token_blacklist.add(credentials.credentials)
    return {"ok": True, "message": "已登出"}


@router.get("/me")
async def get_me(user: User = Depends(require_user)):
    """获取当前用户信息。"""
    return user.to_dict()


# ---------------------------------------------------------------------------
# 管理员路由
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员：列出所有用户。"""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [u.to_dict() for u in users]


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    data: UserUpdateRole,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员：修改用户角色。"""
    if data.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="角色只能是 user 或 admin")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    target.role = data.role
    db.commit()
    return {"ok": True, "user": target.to_dict()}


@router.delete("/users/{user_id}")
async def disable_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员：禁用用户（软删除）。"""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    target.is_active = False
    db.commit()
    return {"ok": True}
