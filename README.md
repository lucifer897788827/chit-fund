# Chit Fund App

## Local Development

- Frontend port: `3000`
- Backend port: `8011`
- Python version: `3.11`

### Frontend

The frontend reads [frontend/.env.development](/E:/chit%20fund%20app/frontend/.env.development) during local development:

```env
REACT_APP_API_URL=http://127.0.0.1:8011
```

### Backend

Local backend runtime is pinned with:

- [backend/runtime.txt](/E:/chit%20fund%20app/backend/runtime.txt)
- [backend/.python-version](/E:/chit%20fund%20app/backend/.python-version)

Start the backend manually with:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8011
```

### One-Command Startup

Use [start-dev.sh](/E:/chit%20fund%20app/start-dev.sh) to start local development. It:

- checks backend/frontend ports before startup
- requires Python `3.11`
- starts backend on `8011`
- starts frontend on `3000`
