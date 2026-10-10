# Makanan — Essential Development & Operations Commands

Quick reference cheat sheet for starting, managing, and debugging the **Makanan** fintech platform.

---

## 1. Docker Backend & Services (Recommended)

All backend components (FastAPI, PostgreSQL 16, Redis 7) run containerized in the sibling repository:
`../Makanan-backend` (or `/home/bilal/bilal_projects/Makanan-backend`).

### Start Services
```bash
# Navigate to the backend repository
cd /home/bilal/bilal_projects/Makanan-backend

# Start all services (Backend + Postgres + Redis) in the background
docker compose up -d

# Check running status and health
docker compose ps
```

### Stop Services
```bash
cd /home/bilal/bilal_projects/Makanan-backend

# Stop all services (preserves database data in docker volumes)
docker compose down

# Stop and wipe database volumes (clean reset)
docker compose down -v
```

### Check Status & Logs
```bash
# Check container status and health
docker compose ps

# Follow live logs from the FastAPI backend
docker compose logs -f backend

# Follow logs from PostgreSQL
docker compose logs -f db

# Follow logs from Redis
docker compose logs -f redis

# Follow logs across all containers
docker compose logs -f
```

### Restart & Rebuild
```bash
# Restart the FastAPI backend
docker compose restart backend

# Rebuild the backend container image after modifying requirements.txt
docker compose build backend && docker compose up -d backend
```

---

## 2. Next.js Frontend

The Next.js 16 frontend runs on Node.js.

```bash
# Install frontend dependencies
npm install

# Start local development server (http://localhost:3000)
npm run dev

# Run production build (validates pages & TypeScript)
npm run build

# Start the production build server
npm run start
```

---

## 3. Alternative: Running FastAPI on Host (Without Docker)

If you prefer developing the Python backend directly on your host machine while keeping Postgres and Redis in Docker:

```bash
# 1. Start Postgres and Redis in Docker
docker compose up -d db redis

# 2. Enter backend directory and create virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Start FastAPI server with live reload on port 8000
uvicorn app.main:app --reload --port 8000
```

---

## 4. Database & Redis Access

### Connect to PostgreSQL (Port 5433)
```bash
# Connect directly inside the Docker container
docker exec -it makanan_postgres psql -U makanan_admin -d makanan

# Or connect using host psql client (mapped to port 5433)
PGPASSWORD=78426dff744565d5f6b91cdb0cdfb6d67de1433d942f3cf9 psql -h localhost -p 5433 -U makanan_admin -d makanan
```

**Common SQL queries:**
```sql
-- View all registered users
SELECT id, email, role, full_name, is_active FROM users;

-- View active meal plans
SELECT id, name, tier, price_myr, credits FROM meal_plans;

-- View student subscriptions
SELECT id, user_id, status, credits_total, credits_used FROM subscriptions;

-- View immutable ledger entries
SELECT id, user_id, description, credits_delta, balance_after, created_at FROM wallet_transactions ORDER BY created_at DESC LIMIT 10;

-- View meal redemptions
SELECT id, user_id, meal_id, status, qr_code, redeemed_at FROM redemptions ORDER BY created_at DESC LIMIT 10;
```

### Connect to Redis
```bash
docker exec -it makanan_redis redis-cli -a e0503fe6910ad0bdb0061a888b50256b4d6fef6b988a8d45
```

---

## 5. Seed Test Accounts

The local database is pre-seeded with test accounts across all three user roles:

| Role | Email | Password | Purpose |
| :--- | :--- | :--- | :--- |
| **Student** | `demo@makanan.app` | `demo1234` | Browse plans, test DuitNow/e-wallet payments, redeem meals |
| **Partner** | `partner@makanan.app` | `partner1234` | Cafeteria counter: scan student QR codes, confirm meals, request payouts |
| **Admin** | `admin@makanan.app` | `admin1234` | Overview metrics, manage student/partner accounts, approve payouts |

---

## 6. URLs & Ports Reference

| Service | URL / Port | Description |
| :--- | :--- | :--- |
| **Next.js Frontend** | `http://localhost:3000` | Student app, Partner portal, Admin portal |
| **FastAPI Backend** | `http://localhost:8000` | Core API service |
| **Interactive API Docs (Swagger)** | `http://localhost:8000/docs` | Test all endpoints interactively in your browser |
| **ReDoc API Documentation** | `http://localhost:8000/redoc` | OpenAPI 3.1 documentation |
| **API Health Check** | `http://localhost:8000/api/v1/health` | Fast status probe |
| **PostgreSQL Database** | `localhost:5433` | Host port (mapped from container port 5432) |
| **Redis Cache** | `localhost:6379` | Token caching & session management |

---

## 7. Quick Smoke Test (CLI)

Verify backend connectivity and payment APIs using curl:

```bash
# 1. Health Probe
curl -s http://localhost:8000/api/v1/health | jq .

# 2. Student Login
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@makanan.app","password":"demo1234"}' | jq .

# 3. Fetch Meal Catalog
curl -s http://localhost:8000/api/v1/meals | jq '.[0]'
```
