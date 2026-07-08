# Backend Docker & Render instructions

This folder contains the FastAPI backend for ExecutiveOS and a `Dockerfile` to build a container suitable for Render.com or local testing.

## Build locally

Build the image (from repository root):

```bash
docker build -t executiveos-backend -f backend/Dockerfile .
```

Run locally (exposes port 8000):

```bash
docker run -p 8000:8000 -e PORT=8000 executiveos-backend
```

Then visit `http://localhost:8000/health` (or the endpoint your app provides).

## Render deployment

This repo includes a `render.yaml` that points the backend service to use the `backend/Dockerfile`. To deploy on Render:

- In Render, create a new Web Service and connect it to this repository.
- Set the service to use Docker (the `render.yaml` in the repo already configures this if you use the manifest).
- If you need environment variables, add them in the Render UI (for example `DATABASE_URL` or `VITE_API_URL` for the frontend).

Render will build the Docker image using `backend/Dockerfile` and run the container with the default command defined in the Dockerfile.
