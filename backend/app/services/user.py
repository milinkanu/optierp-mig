"""User & role-assignment service — Module 01."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthenticationError, DuplicateError, NotFoundError, ValidationError
from app.core.security import CurrentUser, hash_password, verify_password
from app.models.core import Role, User, UserRole
from app.schemas.core import UserCreate, UserUpdate
from app.services.audit import log_audit, serialize_document
from app.services.pagination import paginate


async def _validate_roles(db: AsyncSession, role_names: list[str]) -> None:
    if not role_names:
        return
    existing = set(
        (await db.execute(select(Role.name).where(Role.name.in_(role_names)))).scalars().all()
    )
    missing = [r for r in role_names if r not in existing]
    if missing:
        raise ValidationError(f"Unknown roles: {', '.join(missing)}", field="roles")


async def create_user(db: AsyncSession, payload: UserCreate, acting_user: CurrentUser | None) -> User:
    if await db.scalar(select(User).where(User.email == payload.email.lower())):
        raise DuplicateError("A user with this email already exists", field="email")
    await _validate_roles(db, payload.roles)

    user = User(
        id=uuid.uuid4(),
        email=payload.email.lower(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        hashed_password=hash_password(payload.password),
        language=payload.language,
        time_zone=payload.time_zone,
        default_company_id=payload.default_company_id,
        owner=acting_user.id if acting_user else None,
    )
    db.add(user)
    await db.flush()
    for role in payload.roles:
        db.add(UserRole(user_id=user.id, role=role, company_id=payload.default_company_id))
    await db.flush()
    await log_audit(
        db,
        doctype="User",
        document_id=user.id,
        action="INSERT",
        user_id=acting_user.id if acting_user else user.id,
        company_id=payload.default_company_id,
        data_after={k: v for k, v in serialize_document(user).items() if k != "hashed_password"},
    )
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(
        select(User).options(selectinload(User.roles)).where(User.email == email.lower())
    )
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthenticationError("Incorrect email or password")
    if not user.is_active:
        raise AuthenticationError("User account is disabled")
    user.last_login = datetime.now(UTC)
    await db.commit()
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.scalar(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    )
    if user is None:
        raise NotFoundError("User not found")
    return user


async def list_users(
    db: AsyncSession, page: int = 1, page_size: int = 20, search: str | None = None
) -> tuple[list[User], int]:
    stmt = select(User).order_by(User.email)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            User.email.ilike(like) | User.first_name.ilike(like) | User.last_name.ilike(like)
        )
    return await paginate(db, stmt, page, page_size)


async def update_user(
    db: AsyncSession, user_id: uuid.UUID, payload: UserUpdate, acting_user: CurrentUser
) -> User:
    user = await get_user(db, user_id)
    before = {k: v for k, v in serialize_document(user).items() if k != "hashed_password"}
    data = payload.model_dump(exclude_unset=True)

    roles = data.pop("roles", None)
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.hashed_password = hash_password(password)
    if roles is not None:
        await _validate_roles(db, roles)
        await db.execute(
            delete(UserRole).where(
                UserRole.user_id == user.id, UserRole.company_id == user.default_company_id
            )
        )
        for role in roles:
            db.add(UserRole(user_id=user.id, role=role, company_id=user.default_company_id))
    user.modified_by = acting_user.id
    await db.flush()
    await log_audit(
        db,
        doctype="User",
        document_id=user.id,
        action="UPDATE",
        user_id=acting_user.id,
        company_id=acting_user.company_id,
        data_before=before,
        data_after={k: v for k, v in serialize_document(user).items() if k != "hashed_password"},
    )
    await db.commit()
    return await get_user(db, user.id)
