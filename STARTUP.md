# OrderHub CRM Startup Guide

This guide explains how to start the CRM and troubleshoot common database connectivity issues.

## 🚀 Recommended Development Setup (Fast & Native)

Use this setup for active coding (hot-reloading enabled).

### 1. Prerequisite: Database (Docker)
The database runs in Docker to avoid local Postgres setup issues.
```bash
docker compose up -d postgres
```

### 2. Backend (FastAPI)
Run from the `/backend` directory. Ensure `backend/.env` points to `localhost`:
```bash
# Check backend/.env
DATABASE_URL=postgresql+asyncpg://crm:crm_pass@localhost:5432/crm_db

# Run server
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend (Vite)
Run from the `/frontend` directory:
```bash
cd frontend
npm install
npm run dev
```
Accessible at: **http://localhost:3000**

---

## 🐳 Alternative Setup: Full Docker (Production-ready)
Everything (FE, BE, DB) runs inside Docker.
```bash
docker compose up --build -d
```
*Note: In this mode, the backend uses `postgres` as the database hostname instead of `localhost`.*

---

## 🛠️ Common Issues & Troubleshooting

### "Internal Server Error" on Login
This usually happens because the backend cannot connect to the database.
1. **Check if Postgres is running**: `docker ps`. If not, run `docker compose up -d postgres`.
2. **Check Hostname**: 
   - If running backend **natively** (uvicorn), use `localhost` in `.env`.
   - If running backend **in Docker**, use `postgres` in `.env`.
3. **Database is empty**: If you see login errors despite connection, seed the data:
   ```bash
   cd backend
   python seed.py --if-empty
   ```

## 🔑 Dev Credentials
- **Owner**: `owner@orderhub.dev` / `owner123`
- **Manager**: `manager@orderhub.dev` / `manager123`
- **Designer**: `designer@orderhub.dev` / `designer123`
