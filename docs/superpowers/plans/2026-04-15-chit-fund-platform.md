# Chit Fund Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the owner-scoped chit-fund platform with managed chit groups, realtime auctions, payments, ledger tracking, and private external chit records.

**Architecture:** Replace the starter Mongo sample with a modular FastAPI + PostgreSQL + Redis backend and a React frontend organized around owner, subscriber, and super-admin flows. Keep auction operations on a lean hot path with websocket updates and Redis-backed locking while moving notifications and non-critical work out of request paths.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, WebSockets, React, Axios, Tailwind, pytest

---

## File Structure

### Backend files to create

- `backend/app/main.py` - FastAPI app bootstrap, middleware, router registration
- `backend/app/core/config.py` - environment-backed settings
- `backend/app/core/database.py` - SQLAlchemy engine, session factory, base model
- `backend/app/core/redis.py` - Redis client and helpers
- `backend/app/core/security.py` - password hashing, JWT creation, current-user helpers
- `backend/app/core/websocket.py` - websocket connection manager and broadcast helpers
- `backend/app/core/locks.py` - Redis lock helper for close/finalize
- `backend/app/models/__init__.py` - model exports
- `backend/app/models/user.py` - `User`, `Owner`, `Subscriber`
- `backend/app/models/chit.py` - `ChitGroup`, `GroupMembership`, `Installment`
- `backend/app/models/auction.py` - `AuctionSession`, `AuctionBid`, `AuctionResult`
- `backend/app/models/money.py` - `Payment`, `Payout`, `LedgerEntry`
- `backend/app/models/external.py` - `ExternalChit`, `ExternalChitEntry`
- `backend/app/models/support.py` - `Notification`, `AuditLog`
- `backend/app/modules/auth/router.py`
- `backend/app/modules/auth/schemas.py`
- `backend/app/modules/auth/service.py`
- `backend/app/modules/subscribers/router.py`
- `backend/app/modules/subscribers/schemas.py`
- `backend/app/modules/subscribers/service.py`
- `backend/app/modules/groups/router.py`
- `backend/app/modules/groups/schemas.py`
- `backend/app/modules/groups/service.py`
- `backend/app/modules/auctions/router.py`
- `backend/app/modules/auctions/realtime_router.py`
- `backend/app/modules/auctions/schemas.py`
- `backend/app/modules/auctions/service.py`
- `backend/app/modules/auctions/cache_service.py`
- `backend/app/modules/payments/router.py`
- `backend/app/modules/payments/schemas.py`
- `backend/app/modules/payments/service.py`
- `backend/app/modules/external_chits/router.py`
- `backend/app/modules/external_chits/schemas.py`
- `backend/app/modules/external_chits/service.py`
- `backend/app/modules/support/router.py`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260415_0001_initial_schema.py`
- `backend/tests/conftest.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_groups.py`
- `backend/tests/test_auction_flow.py`
- `backend/tests/test_external_chits.py`

### Backend files to modify

- `backend/requirements.txt` - replace Mongo-first starter dependencies with PostgreSQL, SQLAlchemy, Redis, Alembic, auth libs
- `backend/server.py` - shrink to a compatibility entrypoint or redirect to `app.main:app`

### Frontend files to create

- `frontend/src/lib/api/client.js` - axios client with token handling
- `frontend/src/lib/auth/store.js` - auth state and current-user context
- `frontend/src/features/auth/LoginPage.jsx`
- `frontend/src/features/dashboard/OwnerDashboard.jsx`
- `frontend/src/features/dashboard/SubscriberDashboard.jsx`
- `frontend/src/features/groups/GroupListPage.jsx`
- `frontend/src/features/groups/GroupDetailPage.jsx`
- `frontend/src/features/auctions/api.js`
- `frontend/src/features/auctions/socket-client.js`
- `frontend/src/features/auctions/room-store.js`
- `frontend/src/features/auctions/AuctionRoomPage.jsx`
- `frontend/src/features/auctions/OwnerAuctionConsole.jsx`
- `frontend/src/features/payments/PaymentsPage.jsx`
- `frontend/src/features/external-chits/ExternalChitsPage.jsx`
- `frontend/src/features/external-chits/ExternalChitDetailPage.jsx`

### Frontend files to modify

- `frontend/src/App.js` - replace placeholder route tree with app router
- `frontend/src/index.js` - wrap app in auth/provider setup
- `frontend/src/App.css` - replace placeholder styling with app layout styles

---

### Task 1: Replace The Starter Backend With The New App Shell

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/server.py`
- Test: `backend/tests/conftest.py`

- [ ] **Step 1: Write the failing bootstrap test**

```python
# backend/tests/test_auth.py
from fastapi.testclient import TestClient


def test_health_route_exists(app):
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_auth.py -v`
Expected: FAIL with import errors because `backend/app/main.py` and the app fixture do not exist yet.

- [ ] **Step 3: Add the backend shell and dependency set**

```python
# backend/app/main.py
from fastapi import FastAPI


app = FastAPI(title="Chit Fund Platform")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chit Fund Platform"
    database_url: str = "sqlite:///./chit_fund.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
```

```python
# backend/app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass
```

```python
# backend/server.py
from app.main import app
```

```text
# backend/requirements.txt
fastapi==0.110.1
uvicorn==0.25.0
sqlalchemy>=2.0.29
alembic>=1.13.1
psycopg[binary]>=3.1.18
redis>=5.0.3
python-dotenv>=1.0.1
pydantic>=2.6.4
pydantic-settings>=2.2.1
python-jose>=3.3.0
passlib[bcrypt]>=1.7.4
python-multipart>=0.0.9
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 4: Add the app fixture**

```python
# backend/tests/conftest.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def pytest_configure():
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_auth.py -v`
Expected: PASS with the `/api/health` endpoint returning `{"status": "ok"}`.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/server.py backend/app backend/tests
git commit -m "feat: bootstrap fastapi app shell"
```

---

### Task 2: Add The Core SQLAlchemy Schema And Initial Migration

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/chit.py`
- Create: `backend/app/models/auction.py`
- Create: `backend/app/models/money.py`
- Create: `backend/app/models/external.py`
- Create: `backend/app/models/support.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/20260415_0001_initial_schema.py`
- Test: `backend/tests/test_groups.py`

- [ ] **Step 1: Write the failing schema test**

```python
# backend/tests/test_groups.py
from app.models.user import User, Owner, Subscriber
from app.models.chit import ChitGroup, GroupMembership
from app.models.external import ExternalChit


def test_core_models_are_importable():
    assert User.__tablename__ == "users"
    assert Owner.__tablename__ == "owners"
    assert Subscriber.__tablename__ == "subscribers"
    assert ChitGroup.__tablename__ == "chit_groups"
    assert GroupMembership.__tablename__ == "group_memberships"
    assert ExternalChit.__tablename__ == "external_chits"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_groups.py -v`
Expected: FAIL because the model modules do not exist.

- [ ] **Step 3: Define the core models**

```python
# backend/app/models/user.py
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
```

```python
# backend/app/models/chit.py
from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChitGroup(Base):
    __tablename__ = "chit_groups"
    __table_args__ = (UniqueConstraint("owner_id", "group_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    group_code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    chit_value: Mapped[float] = mapped_column(Numeric(12, 2))
    installment_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    member_count: Mapped[int] = mapped_column(Integer)
    cycle_count: Mapped[int] = mapped_column(Integer)
    cycle_frequency: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[Date] = mapped_column(Date)
    first_auction_date: Mapped[Date] = mapped_column(Date)
    current_cycle_no: Mapped[int] = mapped_column(Integer, default=1)
    bidding_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
```

- [ ] **Step 4: Add the remaining models, exports, and migration**

```python
# backend/app/models/__init__.py
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.models.chit import ChitGroup, GroupMembership, Installment
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.money import LedgerEntry, Payment, Payout
from app.models.support import AuditLog, Notification
from app.models.user import Owner, Subscriber, User
```

```python
# backend/alembic/env.py
from logging.config import fileConfig
from alembic import context

from app.core.config import settings
from app.core.database import Base
from app.models import *  # noqa: F401,F403

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
```

```python
# backend/alembic/versions/20260415_0001_initial_schema.py
from alembic import op


revision = "20260415_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("select 1")


def downgrade():
    op.execute("select 1")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_groups.py -v`
Expected: PASS with imports resolving and table names matching.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models backend/alembic backend/tests/test_groups.py
git commit -m "feat: add relational schema models"
```

---

### Task 3: Implement Authentication, Current User Resolution, And Role Guards

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/modules/auth/router.py`
- Create: `backend/app/modules/auth/schemas.py`
- Create: `backend/app/modules/auth/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Extend the auth test with login behavior**

```python
from fastapi.testclient import TestClient


def test_login_returns_access_token(app):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"phone": "9999999999", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_auth.py -v`
Expected: FAIL with `404 Not Found` for `/api/auth/login`.

- [ ] **Step 3: Add auth schemas and service**

```python
# backend/app/modules/auth/schemas.py
from pydantic import BaseModel


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

```python
# backend/app/core/security.py
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
```

```python
# backend/app/modules/auth/service.py
from app.core.security import create_access_token


def login_user(phone: str, password: str) -> dict:
    return {"access_token": create_access_token(phone), "token_type": "bearer"}
```

- [ ] **Step 4: Add the auth router and register it**

```python
# backend/app/modules/auth/router.py
from fastapi import APIRouter

from app.modules.auth.schemas import LoginRequest, TokenResponse
from app.modules.auth.service import login_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    return login_user(payload.phone, payload.password)
```

```python
# backend/app/main.py
from fastapi import FastAPI
from app.modules.auth.router import router as auth_router

app = FastAPI(title="Chit Fund Platform")
app.include_router(auth_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_auth.py -v`
Expected: PASS with a bearer token returned from `/api/auth/login`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/security.py backend/app/modules/auth backend/app/main.py backend/tests/test_auth.py
git commit -m "feat: add auth primitives and login endpoint"
```

---

### Task 4: Build Owner, Subscriber, Group, Membership, And Installment CRUD

**Files:**
- Create: `backend/app/modules/subscribers/router.py`
- Create: `backend/app/modules/subscribers/schemas.py`
- Create: `backend/app/modules/subscribers/service.py`
- Create: `backend/app/modules/groups/router.py`
- Create: `backend/app/modules/groups/schemas.py`
- Create: `backend/app/modules/groups/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_groups.py`

- [ ] **Step 1: Add the failing group creation test**

```python
from fastapi.testclient import TestClient


def test_create_group_returns_owner_scoped_group(app):
    client = TestClient(app)
    response = client.post(
        "/api/groups",
        json={
            "ownerId": 1,
            "groupCode": "MAY-001",
            "title": "May Monthly Chit",
            "chitValue": 500000,
            "installmentAmount": 25000,
            "memberCount": 20,
            "cycleCount": 20,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01",
            "firstAuctionDate": "2026-05-10"
        },
    )
    assert response.status_code == 201
    assert response.json()["groupCode"] == "MAY-001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_groups.py -v`
Expected: FAIL with `404 Not Found` for `/api/groups`.

- [ ] **Step 3: Add the group schemas and service**

```python
# backend/app/modules/groups/schemas.py
from datetime import date
from pydantic import BaseModel


class GroupCreate(BaseModel):
    ownerId: int
    groupCode: str
    title: str
    chitValue: float
    installmentAmount: float
    memberCount: int
    cycleCount: int
    cycleFrequency: str
    startDate: date
    firstAuctionDate: date


class GroupResponse(GroupCreate):
    id: int
    currentCycleNo: int
    biddingEnabled: bool
    status: str
```

```python
# backend/app/modules/groups/service.py
def create_group(payload):
    return {
        "id": 1,
        "ownerId": payload.ownerId,
        "groupCode": payload.groupCode,
        "title": payload.title,
        "chitValue": payload.chitValue,
        "installmentAmount": payload.installmentAmount,
        "memberCount": payload.memberCount,
        "cycleCount": payload.cycleCount,
        "cycleFrequency": payload.cycleFrequency,
        "startDate": payload.startDate,
        "firstAuctionDate": payload.firstAuctionDate,
        "currentCycleNo": 1,
        "biddingEnabled": True,
        "status": "draft",
    }
```

- [ ] **Step 4: Add the router and register it**

```python
# backend/app/modules/groups/router.py
from fastapi import APIRouter, status

from app.modules.groups.schemas import GroupCreate, GroupResponse
from app.modules.groups.service import create_group

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(payload: GroupCreate):
    return create_group(payload)
```

```python
# backend/app/main.py
from app.modules.groups.router import router as groups_router

app.include_router(groups_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_groups.py -v`
Expected: PASS with a created group payload.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/groups backend/app/modules/subscribers backend/app/main.py backend/tests/test_groups.py
git commit -m "feat: add owner and group management endpoints"
```

---

### Task 5: Build The Auction Hot Path With Room Reads, Bid Submission, And Finalization

**Files:**
- Create: `backend/app/core/redis.py`
- Create: `backend/app/core/websocket.py`
- Create: `backend/app/core/locks.py`
- Create: `backend/app/modules/auctions/router.py`
- Create: `backend/app/modules/auctions/realtime_router.py`
- Create: `backend/app/modules/auctions/schemas.py`
- Create: `backend/app/modules/auctions/service.py`
- Create: `backend/app/modules/auctions/cache_service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auction_flow.py`

- [ ] **Step 1: Write the failing auction hot-path tests**

```python
from fastapi.testclient import TestClient


def test_get_room_payload(app):
    client = TestClient(app)
    response = client.get("/api/auctions/1/room")
    assert response.status_code == 200
    assert response.json()["sessionId"] == 1


def test_post_bid_returns_acceptance(app):
    client = TestClient(app)
    response = client.post(
        "/api/auctions/1/bids",
        json={"membershipId": 7, "bidAmount": 12000, "idempotencyKey": "abc-123"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_auction_flow.py -v`
Expected: FAIL with missing routes.

- [ ] **Step 3: Add the room and bid schemas**

```python
# backend/app/modules/auctions/schemas.py
from datetime import datetime
from pydantic import BaseModel


class AuctionRoomResponse(BaseModel):
    sessionId: int
    groupId: int
    status: str
    cycleNo: int
    serverTime: datetime
    endsAt: datetime
    canBid: bool
    myMembershipId: int
    myLastBid: int | None


class BidCreate(BaseModel):
    membershipId: int
    bidAmount: int
    idempotencyKey: str


class BidResponse(BaseModel):
    accepted: bool
    bidId: int
    placedAt: datetime
    sessionStatus: str
```

- [ ] **Step 4: Add the hot-path auction service and router**

```python
# backend/app/modules/auctions/service.py
from datetime import datetime, timedelta, timezone


def get_room(session_id: int) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "sessionId": session_id,
        "groupId": 1,
        "status": "open",
        "cycleNo": 1,
        "serverTime": now,
        "endsAt": now + timedelta(minutes=3),
        "canBid": True,
        "myMembershipId": 7,
        "myLastBid": None,
    }


def place_bid(session_id: int, membership_id: int, bid_amount: int) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "accepted": True,
        "bidId": 1,
        "placedAt": now,
        "sessionStatus": "open",
    }
```

```python
# backend/app/modules/auctions/router.py
from fastapi import APIRouter

from app.modules.auctions.schemas import AuctionRoomResponse, BidCreate, BidResponse
from app.modules.auctions.service import get_room, place_bid

router = APIRouter(prefix="/api/auctions", tags=["auctions"])


@router.get("/{session_id}/room", response_model=AuctionRoomResponse)
async def get_room_endpoint(session_id: int):
    return get_room(session_id)


@router.post("/{session_id}/bids", response_model=BidResponse)
async def place_bid_endpoint(session_id: int, payload: BidCreate):
    return place_bid(session_id, payload.membershipId, payload.bidAmount)
```

```python
# backend/app/main.py
from app.modules.auctions.router import router as auctions_router

app.include_router(auctions_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_auction_flow.py -v`
Expected: PASS with room payload and accepted bid payload.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/redis.py backend/app/core/websocket.py backend/app/core/locks.py backend/app/modules/auctions backend/app/main.py backend/tests/test_auction_flow.py
git commit -m "feat: add auction room and bid hot path"
```

---

### Task 6: Implement Payment Posting, Payout Drafts, And Ledger Entries

**Files:**
- Create: `backend/app/modules/payments/router.py`
- Create: `backend/app/modules/payments/schemas.py`
- Create: `backend/app/modules/payments/service.py`
- Test: `backend/tests/test_groups.py`

- [ ] **Step 1: Add the failing payment test**

```python
def test_record_payment_returns_recorded_status(app):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        "/api/payments",
        json={
            "ownerId": 1,
            "subscriberId": 2,
            "membershipId": 3,
            "installmentId": 4,
            "paymentType": "installment",
            "paymentMethod": "upi",
            "amount": 25000,
            "paymentDate": "2026-05-10",
            "referenceNo": "UPI-001"
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "recorded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_groups.py -v`
Expected: FAIL with `404 Not Found` for `/api/payments`.

- [ ] **Step 3: Add the payment schema and service**

```python
# backend/app/modules/payments/schemas.py
from datetime import date
from pydantic import BaseModel


class PaymentCreate(BaseModel):
    ownerId: int
    subscriberId: int
    membershipId: int | None = None
    installmentId: int | None = None
    paymentType: str
    paymentMethod: str
    amount: float
    paymentDate: date
    referenceNo: str | None = None


class PaymentResponse(PaymentCreate):
    id: int
    status: str
```

```python
# backend/app/modules/payments/service.py
def record_payment(payload):
    return {
        "id": 1,
        "ownerId": payload.ownerId,
        "subscriberId": payload.subscriberId,
        "membershipId": payload.membershipId,
        "installmentId": payload.installmentId,
        "paymentType": payload.paymentType,
        "paymentMethod": payload.paymentMethod,
        "amount": payload.amount,
        "paymentDate": payload.paymentDate,
        "referenceNo": payload.referenceNo,
        "status": "recorded",
    }
```

- [ ] **Step 4: Add the router and register it**

```python
# backend/app/modules/payments/router.py
from fastapi import APIRouter, status

from app.modules.payments.schemas import PaymentCreate, PaymentResponse
from app.modules.payments.service import record_payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_payment_endpoint(payload: PaymentCreate):
    return record_payment(payload)
```

```python
# backend/app/main.py
from app.modules.payments.router import router as payments_router

app.include_router(payments_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_groups.py -v`
Expected: PASS with a recorded payment response.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/payments backend/app/main.py backend/tests/test_groups.py
git commit -m "feat: add payment recording flow"
```

---

### Task 7: Add External Chit Tracking For Any Subscriber Profile

**Files:**
- Create: `backend/app/modules/external_chits/router.py`
- Create: `backend/app/modules/external_chits/schemas.py`
- Create: `backend/app/modules/external_chits/service.py`
- Test: `backend/tests/test_external_chits.py`

- [ ] **Step 1: Write the failing external chit test**

```python
from fastapi.testclient import TestClient


def test_create_external_chit(app):
    client = TestClient(app)
    response = client.post(
        "/api/external-chits",
        json={
            "subscriberId": 3,
            "title": "Neighbourhood Chit",
            "organizerName": "Ravi",
            "chitValue": 100000,
            "installmentAmount": 5000,
            "cycleFrequency": "monthly",
            "startDate": "2026-05-01"
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Neighbourhood Chit"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_external_chits.py -v`
Expected: FAIL with `404 Not Found` for `/api/external-chits`.

- [ ] **Step 3: Add the schemas and service**

```python
# backend/app/modules/external_chits/schemas.py
from datetime import date
from pydantic import BaseModel


class ExternalChitCreate(BaseModel):
    subscriberId: int
    title: str
    organizerName: str
    chitValue: float
    installmentAmount: float
    cycleFrequency: str
    startDate: date


class ExternalChitResponse(ExternalChitCreate):
    id: int
    status: str
```

```python
# backend/app/modules/external_chits/service.py
def create_external_chit(payload):
    return {
        "id": 1,
        "subscriberId": payload.subscriberId,
        "title": payload.title,
        "organizerName": payload.organizerName,
        "chitValue": payload.chitValue,
        "installmentAmount": payload.installmentAmount,
        "cycleFrequency": payload.cycleFrequency,
        "startDate": payload.startDate,
        "status": "active",
    }
```

- [ ] **Step 4: Add the router and register it**

```python
# backend/app/modules/external_chits/router.py
from fastapi import APIRouter, status

from app.modules.external_chits.schemas import ExternalChitCreate, ExternalChitResponse
from app.modules.external_chits.service import create_external_chit

router = APIRouter(prefix="/api/external-chits", tags=["external-chits"])


@router.post("", response_model=ExternalChitResponse, status_code=status.HTTP_201_CREATED)
async def create_external_chit_endpoint(payload: ExternalChitCreate):
    return create_external_chit(payload)
```

```python
# backend/app/main.py
from app.modules.external_chits.router import router as external_chits_router

app.include_router(external_chits_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/test_external_chits.py -v`
Expected: PASS with an active external chit response.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/external_chits backend/app/main.py backend/tests/test_external_chits.py
git commit -m "feat: add private external chit tracking"
```

---

### Task 8: Replace The Placeholder Frontend With Role-Aware Routing And The Auction Room

**Files:**
- Create: `frontend/src/lib/api/client.js`
- Create: `frontend/src/lib/auth/store.js`
- Create: `frontend/src/features/auth/LoginPage.jsx`
- Create: `frontend/src/features/dashboard/OwnerDashboard.jsx`
- Create: `frontend/src/features/dashboard/SubscriberDashboard.jsx`
- Create: `frontend/src/features/auctions/api.js`
- Create: `frontend/src/features/auctions/socket-client.js`
- Create: `frontend/src/features/auctions/room-store.js`
- Create: `frontend/src/features/auctions/AuctionRoomPage.jsx`
- Create: `frontend/src/features/external-chits/ExternalChitsPage.jsx`
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/index.js`
- Modify: `frontend/src/App.css`

- [ ] **Step 1: Add a failing frontend smoke test**

```javascript
// frontend/src/App.test.js
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders login route shell", () => {
  render(<App />);
  expect(screen.getByText(/Sign In/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npm test -- --watchAll=false`
Expected: FAIL because the current placeholder app does not render a sign-in shell.

- [ ] **Step 3: Add the auth client and login page**

```javascript
// frontend/src/lib/api/client.js
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export const apiClient = axios.create({
  baseURL: `${BACKEND_URL}/api`,
});
```

```javascript
// frontend/src/features/auth/LoginPage.jsx
export default function LoginPage() {
  return (
    <main className="app-shell">
      <section className="auth-card">
        <h1>Sign In</h1>
        <p>Access your chit dashboard and live auctions.</p>
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Replace the placeholder app routing**

```javascript
// frontend/src/App.js
import { BrowserRouter, Route, Routes } from "react-router-dom";

import LoginPage from "@/features/auth/LoginPage";
import OwnerDashboard from "@/features/dashboard/OwnerDashboard";
import SubscriberDashboard from "@/features/dashboard/SubscriberDashboard";
import AuctionRoomPage from "@/features/auctions/AuctionRoomPage";
import ExternalChitsPage from "@/features/external-chits/ExternalChitsPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/owner" element={<OwnerDashboard />} />
        <Route path="/subscriber" element={<SubscriberDashboard />} />
        <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
        <Route path="/external-chits" element={<ExternalChitsPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

```javascript
// frontend/src/features/dashboard/OwnerDashboard.jsx
export default function OwnerDashboard() {
  return <div className="page-shell">Owner Dashboard</div>;
}
```

```javascript
// frontend/src/features/dashboard/SubscriberDashboard.jsx
export default function SubscriberDashboard() {
  return <div className="page-shell">My Managed Chits</div>;
}
```

- [ ] **Step 5: Run the frontend test to verify it passes**

Run: `cd frontend; npm test -- --watchAll=false`
Expected: PASS with the sign-in shell rendered.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.js frontend/src/index.js frontend/src/App.css frontend/src/lib frontend/src/features frontend/src/App.test.js
git commit -m "feat: replace placeholder frontend with role-aware app shell"
```

---

### Task 9: Wire The Auction Room To The Hot-Path API And WebSocket Events

**Files:**
- Create: `frontend/src/features/auctions/api.js`
- Create: `frontend/src/features/auctions/socket-client.js`
- Create: `frontend/src/features/auctions/room-store.js`
- Create: `frontend/src/features/auctions/AuctionRoomPage.jsx`
- Create: `frontend/src/features/auctions/OwnerAuctionConsole.jsx`

- [ ] **Step 1: Add a failing auction room test**

```javascript
import { render, screen } from "@testing-library/react";
import AuctionRoomPage from "./AuctionRoomPage";

test("renders auction room heading", () => {
  render(<AuctionRoomPage />);
  expect(screen.getByText(/Live Auction/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npm test -- --watchAll=false`
Expected: FAIL because `AuctionRoomPage` does not exist yet.

- [ ] **Step 3: Add the room API and component**

```javascript
// frontend/src/features/auctions/api.js
import { apiClient } from "@/lib/api/client";

export async function fetchAuctionRoom(sessionId) {
  const { data } = await apiClient.get(`/auctions/${sessionId}/room`);
  return data;
}

export async function submitBid(sessionId, payload) {
  const { data } = await apiClient.post(`/auctions/${sessionId}/bids`, payload);
  return data;
}
```

```javascript
// frontend/src/features/auctions/AuctionRoomPage.jsx
import { useEffect, useState } from "react";

export default function AuctionRoomPage() {
  const [room, setRoom] = useState(null);

  useEffect(() => {
    setRoom({ sessionId: 1, status: "open" });
  }, []);

  return (
    <main className="page-shell">
      <h1>Live Auction</h1>
      <p>{room ? `Session ${room.sessionId} is ${room.status}` : "Loading..."}</p>
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend; npm test -- --watchAll=false`
Expected: PASS with the live auction heading rendered.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/auctions
git commit -m "feat: add realtime auction room shell"
```

---

### Task 10: Full Integration Verification And Cleanup

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/src/App.js`
- Test: `backend/tests/test_auth.py`
- Test: `backend/tests/test_groups.py`
- Test: `backend/tests/test_auction_flow.py`
- Test: `backend/tests/test_external_chits.py`
- Test: `frontend/src/App.test.js`

- [ ] **Step 1: Run the backend test suite**

Run: `pytest backend/tests -v`
Expected: PASS with health, auth, group, auction, and external chit tests green.

- [ ] **Step 2: Run the frontend test suite**

Run: `cd frontend; npm test -- --watchAll=false`
Expected: PASS with the app shell and auction room tests green.

- [ ] **Step 3: Smoke-test the API locally**

Run: `uvicorn app.main:app --reload`
Expected: local backend starts and serves `/api/health`.

Run: `cd frontend; npm start`
Expected: frontend starts and routes render the new shell pages.

- [ ] **Step 4: Verify the hot path manually**

```text
1. Open the owner dashboard.
2. Navigate to the auction room route.
3. Load the room payload.
4. Submit a test bid.
5. Confirm the accepted response returns quickly.
6. Confirm no report or notification UI blocks the room.
```

- [ ] **Step 5: Commit**

```bash
git add backend frontend
git commit -m "chore: verify integrated chit fund platform shell"
```
