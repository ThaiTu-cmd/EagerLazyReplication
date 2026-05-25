# EagerLazyReplication

## Run on a new machine

Requirements:

- Docker Desktop (with Compose)

Steps:

1. Open terminal in project root.
2. Run:
   - `docker compose up -d --build`
3. Open dashboard:
   - http://localhost:8001/

## Useful commands

- Stop all services:
  - `docker compose down`
- Reset all node data from API:
  - `curl -X POST http://localhost:8001/reset-all`
- Rebuild cleanly after code changes:
  - `docker compose down`
  - `docker compose up -d --build`

## Notes

- Each node stores SQLite data in its own named volume:
  - `node_a_data`, `node_b_data`, `node_c_data`
- Build context is limited by `node_app/.dockerignore` for faster and cleaner image builds.
