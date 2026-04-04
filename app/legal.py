"""
app/legal.py
Юридические страницы: реквизиты, оферта, соглашение, политика ПД.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["legal"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/requisites", response_class=HTMLResponse)
async def requisites(request: Request):
    return templates.TemplateResponse("requisites.html", {"request": request})


@router.get("/offer", response_class=HTMLResponse)
async def offer(request: Request):
    return templates.TemplateResponse("offer.html", {"request": request})


@router.get("/agreement", response_class=HTMLResponse)
async def agreement(request: Request):
    return templates.TemplateResponse("agreement.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
