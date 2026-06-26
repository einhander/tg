from fastapi import APIRouter

from tgapp.web.routes.effects import router as effects_router
from tgapp.web.routes.exports import router as exports_router
from tgapp.web.routes.pages import router as pages_router
from tgapp.web.routes.processing import router as processing_router
from tgapp.web.routes.uploads import router as uploads_router

router = APIRouter()
router.include_router(pages_router)
router.include_router(uploads_router)
router.include_router(processing_router)
router.include_router(effects_router)
router.include_router(exports_router)
