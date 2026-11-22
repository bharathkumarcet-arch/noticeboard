import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db
from app.routes import auth, notices, faculty, uploads, pages

# Ensure database tables exist immediately on startup
init_db()

app = FastAPI(
    title=settings.APP_NAME,
    description="Full-stack portal for publishing notices and tracking student readership.",
    version="1.0.0"
)

# Static assets
static_dir = settings.BASE_DIR / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount API Routers
app.include_router(auth.router)
app.include_router(notices.router)
app.include_router(faculty.router)
app.include_router(uploads.router)

# Mount HTML page views
app.include_router(pages.router)

templates = Jinja2Templates(directory=str(settings.BASE_DIR / "app" / "templates"))

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={
                "request": request,
                "user": None,
                "app_name": settings.APP_NAME,
                "college_name": settings.COLLEGE_NAME,
                "error": "The page or notice you are looking for does not exist."
            },
            status_code=404
        )
    return HTMLResponse(content='{"detail": "Not Found"}', status_code=404, media_type="application/json")

@app.exception_handler(500)
@app.exception_handler(Exception)
async def custom_500_handler(request: Request, exc):
    import traceback
    traceback.print_exc()
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="500.html",
            context={
                "request": request,
                "user": None,
                "app_name": settings.APP_NAME,
                "college_name": settings.COLLEGE_NAME,
                "error": str(exc)
            },
            status_code=500
        )
    return HTMLResponse(content=f'{{"detail": "Internal Server Error: {str(exc)}"}}', status_code=500, media_type="application/json")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
