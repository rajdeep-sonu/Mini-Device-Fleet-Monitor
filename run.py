"""Application entry point – start FastAPI server with uvicorn."""

import uvicorn
from app.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
