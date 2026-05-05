from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from io import BytesIO
from fastapi import UploadFile, File
from google.genai import errors as genai_errors

from .pdf_generator import generate_delivery_slip
from .extractor import extract_order, extract_order_from_image, ExtractedOrder

app = FastAPI(title="DM2Order API", version="0.1.0")

# Allow the frontend (running on a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    message: str


def _user_friendly_error(exc: Exception) -> tuple[int, str]:
    """Translate an exception into (http_status_code, user_message)."""
    if isinstance(exc, genai_errors.APIError):
        status = getattr(exc, "code", None)
        if status == 503 or status == 429 or status == 500 or status == 502 or status == 504:
            return 503, "Our AI is busy right now. Please try again in a moment."
        if status == 400:
            return 400, "We couldn't understand this message. Try cleaning it up and pasting again."
        if status in (401, 403):
            return 500, "Server configuration issue. Please contact support."
    return 500, "Something went wrong on our side. Please try again."


@app.get("/")
def health_check():
    return {"status": "ok", "service": "dm2order"}

@app.post("/api/extract")
def extract_endpoint(request: ExtractRequest) -> dict:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    if len(request.message) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 chars)")
    
    try:
        result = extract_order(request.message)
        return result.model_dump() # Pydantic model → plain dict
    except Exception as e:
        status, msg = _user_friendly_error(e)
        print(f"[error] /api/extract failed: {e}")
        raise HTTPException(status_code=status, detail=msg)
    


@app.post("/api/extract-image")
async def extract_image_endpoint(file: UploadFile = File(...)) -> dict:
    """Extract a structured order from a screenshot of a customer DM."""

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail=f"File must be an image. Got: {file.content_type}",
        )
    
    # Validate size (max 5 MB)
    image_bytes = await file.read()
    if len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 5 MB)")
    
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Image file is empty")
    
    try:
        result = extract_order_from_image(image_bytes, file.content_type)
        return result.model_dump()
    except Exception as e:
        status, msg = _user_friendly_error(e)
        print(f"[error] /api/extract failed: {e}")
        raise HTTPException(status_code=status, detail=msg)
    
@app.post("/api/delivery-slip")
def delivery_slip_endpoint(order: dict):
    """Generate and return a PDF delivery slip from an extracted order."""
    try:
        pdf_bytes = generate_delivery_slip(order)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="delivery-slip.pdf"'},
    )