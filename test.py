import os
import uvicorn
from fastapi import FastAPI
from fastapi_access_middleware import AccessMiddleware

app = FastAPI()
app.add_middleware(
    AccessMiddleware,
    service_name="test",
    nats_subject="oops.auth-v2.url-check",
    nats_servers=os.getenv("NATS_SERVERS"),
)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
