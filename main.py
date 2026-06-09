"""
main.py
Punto de entrada del servidor web. Acá vive el webhook de WhatsApp.
Por ahora es un placeholder mínimo — el código del webhook se suma
cuando lleguen las credenciales de Meta.

Para correr localmente:
    uvicorn main:app --reload --port 8000

Para producción (Cloud Run):
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI


app = FastAPI(title="Toni", version="0.1.0")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Toni",
        "env": os.environ.get("ENV", "development"),
        "version": "0.1.0",
    }


@app.get("/health")
async def health():
    """Endpoint de healthcheck para Cloud Run."""
    return {"status": "healthy"}


# TODO: agregar acá el endpoint /webhook cuando lleguen las credenciales de Meta.
# @app.post("/webhook")
# async def whatsapp_webhook(request: Request): ...
