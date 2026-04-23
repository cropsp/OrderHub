---
name: crm-startup-orchestrator
description: |
  Automatically starts the OrderHub CRM by reading instructions from STARTUP.md.
  Activate when the user asks to: "start CRM", "launch the system", "run OrderHub",
  "запусти CRM", "підніми систему".
  This skill ensures that Docker, Backend, and Frontend are started in the correct order.
allowed-tools:
  - Read
  - Bash
  - RunCommand
---

# CRM Startup Orchestrator

This skill is designed to automate the multi-step startup process defined in `STARTUP.md`.

## When to Activate

- When the user wants to start the entire development environment.
- When the user reports that some services are down and needs a "cold start".
- After a fresh clone of the repository.

## Execution Flow

1. **Analyze**: Read `STARTUP.md` to identify the current recommended startup commands.
2. **Orchestrate**:
   - Start the PostgreSQL container first (Prerequisite).
   - Start the Backend (uvicorn) in a persistent terminal named `backend-terminal`.
   - Start the Frontend (npm run dev) in a persistent terminal named `frontend-terminal`.
3. **Verify**: Perform health checks (curl) on both services to ensure they are up.

## Key Resources

- `STARTUP.md`: The source of truth for startup commands.
- `skills/crm-start/scripts/startup_orchestrator.py`: Python helper for automated parsing and execution.

## Troubleshooting

If startup fails:
- Check if Docker is running.
- Ensure ports 5432, 8000, and 3000 are not occupied.
- Review `backend/logs/server.log` for database connectivity issues.
