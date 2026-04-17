import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="E-Commerce API", version="1.0.0")

# CORS - permitir peticiones desde Nginx
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ecommerce_user:ecommerce_pass@postgres:5432/ecommerce_db"
)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend funcionando correctamente"}


@app.get("/api/productos")
def listar_productos():
    # TODO: conectar a PostgreSQL y consultar productos reales
    return {
        "productos": [
            {"id": 1, "nombre": "Laptop Gaming", "precio": 2999.99},
            {"id": 2, "nombre": "Mouse Inalámbrico", "precio": 49.99},
            {"id": 3, "nombre": "Teclado Mecánico", "precio": 129.99},
        ]
    }
