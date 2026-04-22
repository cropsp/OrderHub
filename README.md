# OrderHub CRM

Self-hosted Order Management CRM для управління замовленнями handmade бізнесу з виробництва.

## 🌟 Key Features

- **Dashboard**: Візуалізація статистики замовлень у реальному часі.
- **Pipeline Management**: Гнучке управління статусами замовлень (Нові, В роботі, Готові, Відправлені).
- **Attachment System**: Централізоване сховище для виробничих файлів та макетів.
- **AI Integration (MCP)**: Власний MCP-сервер, що дозволяє AI-агентам аналізувати дані та допомагати в управлінні.
- **Security First**: Повна авторизація на базі JWT для всіх API-ендпоїнтів, включаючи MCP.

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2 (async), PostgreSQL 16 / SQLite |
| **Frontend** | React 19, TypeScript, Vite, Vanilla CSS |
| **Infrastructure** | Docker, Docker Compose, Alembic (migrations) |
| **AI Protocol** | Model Context Protocol (MCP) via SSE |

## 🚀 Швидкий старт

Для детальних інструкцій з локального запуску та налаштування середовища дивіться [STARTUP.md](./STARTUP.md).

### 1. Клонувати та налаштувати

```bash
git clone <repo-url> OrderHub
cd OrderHub
cp backend/.env.example backend/.env
```

### 2. Запустити через Docker (Рекомендовано)

```bash
docker compose -f docker-compose.dev.yml up --build
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs

### 3. Дефолтні облікові записи (dev)

| Email | Password | Role |
|-------|----------|------|
| `owner@orderhub.dev` | `owner123` | Owner (Full Access) |
| `manager@orderhub.dev` | `manager123` | Manager |
| `designer@orderhub.dev` | `designer123` | Designer |

## 🔐 Security & Hardening

Проект пройшов етап безпекового загартовування:
- **JWT Auth**: Всі чутливі дані захищені токенами доступу.
- **MCP Guard**: Ендпоїнти `/api/mcp/sse` та `/api/mcp/messages` вимагають авторизації, що запобігає несанкціонованому доступу AI-агентів.
- **SRP Architecture**: Фронтенд-компоненти рефакторизовані за принципом єдиної відповідальності для підвищення стабільності.

## 🤖 AI & MCP Server

OrderHub виставляє MCP сервер для підключення AI-агентів (Claude Desktop, Hermes тощо) через протокол SSE.

**Ендпоїнти:**
- SSE Connection: `GET /api/mcp/sse`
- Message Channel: `POST /api/mcp/messages`

*Примітка: Для підключення агент повинен передати валідний JWT токен у заголовку Authorization.*

## 📂 Структура проекту

- `/backend`: FastAPI додаток, моделі бази даних та MCP сервер.
- `/frontend`: React додаток з сучасним інтерфейсом.
- `/docs`: Документація та звіти (включаючи аудити безпеки).
- `/scratch`: Тимчасові діагностичні скрипти (ігноруються Git).

## ⚖️ Ліцензія

Private project. All rights reserved.
