import os
import json
from typing import Optional, Literal
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors as genai_errors
from pydantic import BaseModel
import time
import random

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

def call_gemini_with_retry(call_fn, max_attempts: int = 4):
    """
    Run a Gemini API call with exponential backoff on transient errors.
    
    call_fn: a zero-arg function that makes the API call.
    Returns the API response on success, raises on permanent failure.
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return call_fn()
        except genai_errors.APIError as e:
            last_exception = e
            status = getattr(e, "code", None)

            if status not in RETRYABLE_STATUS_CODES:
                raise

            if attempt == max_attempts - 1:
                break

            wait = (2 ** attempt) + random.random()
            print(f"[retry] Gemini returned {status}, retrying in {wait:.1f}s (attempt {attempt + 1}/{max_attempts})")
            time.sleep(wait)

    if last_exception is None:
        raise RuntimeError("call_gemini_with_retry exhausted retries with no exception captured")
    raise last_exception


class OrderItem(BaseModel):
    product: str
    variant: Optional[str] = None
    quantity: int = 1
    price: Optional[float] = None

class ExtractedOrder(BaseModel):
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    governorate: Optional[str] = None
    address: Optional[str] = None
    items: list[OrderItem] = []
    total_price: Optional[float] = None
    notes: Optional[str] = None
    language_detected: Literal["darija", "french", "arabic", "darija_french", "arabic_french", "mixed"]

PROMPT = """You are an order-extraction assistant for Tunisian small businesses.
Sellers receive customer DMs in a mix of Tunisian Darija, French, and Arabic.

Extract structured order data from the message below.

Rules:
- If a field is not mentioned, leave it null. Never guess or hallucinate.
- Phone numbers: strip spaces, dashes, and the +216 country code. Return 8 digits.
- Governorate: use French spelling. Recognize: Sfax, Sousse, Tunis, Ariana, Ben Arous,
  Manouba, Nabeul, Bizerte, Beja, Jendouba, Kef, Siliana, Kairouan, Kasserine,
  Sidi Bouzid, Mahdia, Monastir, Gafsa, Tozeur, Kebili, Gabes, Medenine, Tataouine, Zaghouan.
  If the customer mentions a city that's not a governorate, infer the governorate.
- Items: extract EVERY product mentioned, even across multiple lines or bullets.
- Quantity defaults to 1 unless explicit.
- Do not auto-calculate total_price by summing items. Only fill it if the customer explicitly states a total.

Message:
\"\"\"
{message}
\"\"\"
"""


def extract_order(message: str) -> ExtractedOrder:
    """Extract a structured order from a customer DM."""


    def call():
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=PROMPT.format(message=message),
            config={
                "response_mime_type": "application/json",
                "response_schema": ExtractedOrder,            
            }
        )
    
    response = call_gemini_with_retry(call)
    if response.text is None:
        raise ValueError("Gemini returned an empty response")
    return ExtractedOrder.model_validate_json(response.text)


def extract_order_from_image(image_bytes: bytes, mime_type: str) -> ExtractedOrder:
    """Extract a structured order from a screenshot of a customer DM."""
    image_prompt = """You are an order-extraction assistant for Tunisian small businesses.
    This image is a screenshot of a customer DM (Instagram, WhatsApp, Facebook, or similar).

    The conversation has TWO parties:
    - The CUSTOMER: the one placing the order
    - The SELLER: the business owner using this tool

    Your job is to extract the CUSTOMER's final order, using BOTH sides of the conversation as context.

    How to identify each party:
    - In most chat UIs, one side's bubbles are aligned right (usually the device owner — likely the seller)
    and the other side's bubbles are aligned left (the customer).
    - The seller often replies with prices, availability, sizes, colors, confirmations.
    - The customer typically asks about products, gives their address, gives their phone number.
    - If the layout is unclear, infer roles from message content (who is asking vs. answering).

    How to combine information:
    - Use the CUSTOMER's messages as the primary source of truth for what they want.
    - Use the SELLER's messages to FILL IN missing details ONLY when the customer has implicitly or explicitly agreed:
        * Price: if the seller quotes a price and the customer continues the order (gives address, says "ok", "tamem", "d'accord", "naheb", etc.), use that price.
        * Variant (size, color, model): if the seller offers options and the customer picks one, use the picked variant.
        * Product name: if the customer says "the dress" and the seller's earlier message names it ("la robe rouge"), combine them.
        * Quantity: same logic — agreed-upon quantities win.
    - DO NOT assume the customer agreed to something they didn't respond to.
    - DO NOT extract the seller's offerings as the order. The seller saying "j'ai en M, L, XL" is not a size selection.
    - If the customer rejects something ("non, je veux la noire pas la rouge"), the rejection wins.

    Rules for fields:
    - If a field is genuinely not derivable from the conversation, leave it null. Never guess.
    - Phone numbers: strip spaces, dashes, and the +216 country code. Return 8 digits.
    - Governorate: use French spelling. Recognize: Sfax, Sousse, Tunis, Ariana, Ben Arous,
    Manouba, Nabeul, Bizerte, Beja, Jendouba, Kef, Siliana, Kairouan, Kasserine,
    Sidi Bouzid, Mahdia, Monastir, Gafsa, Tozeur, Kebili, Gabes, Medenine, Tataouine, Zaghouan.
    If a city is mentioned that's not a governorate, infer the governorate.
    - Items: extract every distinct product the customer ordered. Combine seller-provided details (price, variant) with customer-stated quantity/identity.
    - Quantity defaults to 1 unless explicit.
    - total_price: only fill if the conversation explicitly states an order total (not an item-level price).
    - notes: include things like delivery urgency, special requests, and any agreed-upon delivery dates from either party.
    """
    def call():
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part(text=image_prompt),
                types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes)),
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": ExtractedOrder,
            }
            
        )
    
    response = call_gemini_with_retry(call)
    if response.text is None:
        raise ValueError("Gemini returned an empty response")
    return ExtractedOrder.model_validate_json(response.text)
    

if __name__ == "__main__":
    # Test message -- replace this with whatever you want to try
    test_message = """commande:
- 1 robe rouge taille M = 80dt
- 2 echarpes = 30dt
adresse: cite olympique tunis, immeuble A apt 5
mariem ben ali, 27 654 321
livraison rapide stp"""

    result = extract_order(test_message)
    # .model_dump_json formats Pydantic objects as nice JSON
    print(result.model_dump_json(indent=2))


