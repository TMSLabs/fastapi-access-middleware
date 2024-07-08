import os
import uvicorn
from fastapi import FastAPI
from fastapi_access_middleware import AccessMiddleware

app = FastAPI()


@app.get("/")
async def read_root():
    return {"Hello": "World"}


app.add_middleware(
    AccessMiddleware,
    service_name="test_service",
    nats_subject="access",
    nats_servers=["nats://localhost:4222"],
    test=False,
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
