# Makanan Backend (FastAPI + PostgreSQL + Redis)

Authoritative fintech backend for the **Makanan** student meal platform.

## Architecture
- **Framework:** FastAPI (Python 3.12, Async/Await)
- **Database:** PostgreSQL 16 (SQLAlchemy 2.0 Async, AsyncPG)
- **Cache & Rate-limiting:** Redis 7
- **Payment Rails:** Malaysian DuitNow QR (EMVCo standard) & Malaysian E-Wallets (Touch 'n Go, GrabPay, ShopeePay)
- **Security:** HMAC-SHA256 time-limited dynamic QR meal tokens, Double-entry accounting ledger in `wallet_transactions`, Row-level locking (`SELECT ... FOR UPDATE`) to prevent race conditions.

## Quick Start (Docker)
```bash
# 1. Copy environment variables (if not already set)
cp .env.example .env

# 2. Start all services in the background
docker compose up -d

# 3. View live server logs
docker compose logs -f backend
```

## Endpoints & Documentation
- **Interactive Swagger UI:** http://localhost:8000/docs
- **ReDoc Documentation:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/api/v1/health
