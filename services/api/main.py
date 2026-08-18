from fastapi import FastAPI

from services.api.routers.suppliers import router as suppliers_router

app = FastAPI(title="TrackFlow Suppliers API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(suppliers_router)
