# OrderHub CRM

Self-hosted Order Management CRM для управління замовленнями handmade бізнесу шкіряних виробів. Замінює workflow **Etsy CSV → Google Sheets → Trello** єдиним веб-додатком.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), PostgreSQL 16 |
| Frontend | React 19, TypeScript, Vite, TailwindCSS v4 |
| Infrastructure | Docker, Docker Compose |
| AI Integration | MCP Server (Model Context Protocol) |

## Швидкий старт

### Вимоги

- Docker & Docker Compose
- (Опціонально) Node.js 22+ та Python 3.12+ для локального запуску

### 1. Клонувати та налаштувати

```bash
git clone <repo-url> OrderHub
cd OrderHub
cp .env.example .env
```

### 2. Згенерувати ключі безпеки

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Скопіюйте згенеровані значення в `.env` файл.

### 3. Запустити (розробка)

```bash
docker compose -f docker-compose.dev.yml up --build
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs

### 4. Дефолтні облікові записи (dev)

| Email | Password | Role |
|-------|----------|------|
| owner@crm.local | owner123 | Owner (повний доступ) |
| manager@crm.local | manager123 | Manager |
| designer@crm.local | designer123 | Designer |

## Alembic міграції

```bash
# Створити нову міграцію
docker compose exec backend alembic revision --autogenerate -m "description"

# Застосувати міграції
docker compose exec backend alembic upgrade head

# Скасувати останню міграцію
docker compose exec backend alembic downgrade -1
```

## MCP Server

OrderHub виставляє MCP сервер для підключення AI-агентів (Hermes, Claude Desktop, тощо).

Порт: `MCP_SERVER_PORT` (default: 3001)

## Ліцензія

Private project.
