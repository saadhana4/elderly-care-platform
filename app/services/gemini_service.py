"""Gemini AI Service: Plain-language explanations of medications for elderly patients.

Explains:
1. What is this medicine for?
2. Common side effects in everyday language.
3. What to avoid / precautions.
Includes a clear, prominent medical disclaimer.
"""

import json
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = (
    "Medical Disclaimer: This information is AI-generated for educational purposes only. "
    "It is not medical advice, diagnosis, or treatment. Always consult your doctor or pharmacist "
    "before making any changes to your medication routine."
)

# Curated high-accuracy fallbacks for common senior medications when API key is unset or offline
COMMON_MEDICATIONS_FALLBACK = {
    "metformin": {
        "purpose": "Helps lower and balance blood sugar levels by helping your body respond better to insulin.",
        "side_effects": "Mild stomach upset, nausea, loose stools, or metallic taste (especially when first starting).",
        "precautions": "Take with meals to prevent stomach upset. Drink plenty of water and avoid drinking heavy amounts of alcohol.",
    },
    "lisinopril": {
        "purpose": "Lowers high blood pressure and protects your heart and kidneys from extra strain.",
        "side_effects": "Dizziness when standing up too quickly, headache, or a dry tickling cough.",
        "precautions": "Stand up slowly to avoid dizziness. Do not use salt substitutes containing potassium without consulting your doctor.",
    },
    "atorvastatin": {
        "purpose": "Lowers 'bad' cholesterol and protects your blood vessels and heart health.",
        "side_effects": "Mild muscle soreness, joint discomfort, or minor digestive changes.",
        "precautions": "Avoid large amounts of grapefruit or grapefruit juice, as it can increase medicine levels in your bloodstream.",
    },
    "amlodipine": {
        "purpose": "Relaxes your blood vessels so your heart does not have to pump as hard, reducing blood pressure.",
        "side_effects": "Swelling in ankles or lower legs, feeling flushed, or lightheadedness.",
        "precautions": "Keep your legs elevated when resting if mild swelling occurs. Rise slowly from sitting or lying down.",
    },
    "aspirin": {
        "purpose": "Helps prevent blood clots from forming, protecting against heart attacks and strokes.",
        "side_effects": "Easy bruising, minor stomach irritation, or slight heartburn.",
        "precautions": "Take with food or a glass of water. Avoid taking other NSAID pain relievers (like ibuprofen) without doctor guidance.",
    },
    "omeprazole": {
        "purpose": "Reduces stomach acid to prevent heartburn, acid reflux, and protect the stomach lining.",
        "side_effects": "Mild headache, gas, stomach cramps, or mild diarrhea.",
        "precautions": "Usually best taken 30 to 60 minutes before breakfast. Speak to your doctor if you take it for longer than a few weeks.",
    },
    "levothyroxine": {
        "purpose": "Replaces the natural thyroid hormone your body needs for daily energy and metabolism.",
        "side_effects": "Usually very well tolerated; rarely mild jitters or palpitations if the dose needs adjusting.",
        "precautions": "Take first thing in the morning on an empty stomach with a full glass of water, at least 30-60 minutes before breakfast.",
    },
}


def _get_fallback_explanation(med_name: str) -> Dict[str, Any]:
    """Provide a safe, clear explanation template if Gemini is unavailable."""
    clean_name = med_name.strip().lower()
    
    # Check if we have an exact or partial match in curated knowledge base
    for key, data in COMMON_MEDICATIONS_FALLBACK.items():
        if key in clean_name:
            return {
                "purpose": data["purpose"],
                "side_effects": data["side_effects"],
                "precautions": data["precautions"],
                "disclaimer": DISCLAIMER_TEXT,
                "source": "curated_guide",
            }

    # Universal senior-friendly explanation template
    return {
        "purpose": f"Prescribed to help manage health symptoms and support recovery as instructed by your doctor.",
        "side_effects": "May include mild drowsiness, dizziness, or stomach sensitivity. Reactions vary for each person.",
        "precautions": "Take with water as directed. Never double up on missed doses. Always check with your pharmacist before taking new supplements.",
        "disclaimer": DISCLAIMER_TEXT,
        "source": "general_guide",
    }


def explain_medication(name: str, dosage: str = "", notes: str = "") -> Dict[str, Any]:
    """Generate a plain-language explanation of a medication using Gemini API.
    
    Returns structured JSON with purpose, side effects, precautions, and medical disclaimer.
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set. Using curated healthcare fallback for %s.", name)
        return _get_fallback_explanation(name)

    prompt = f"""
You are an empathetic, clear geriatric healthcare educator speaking directly to an elderly patient and their family.
Explain the following medication in simple, calm, 6th-grade reading level language:

Medication: {name}
Dosage: {dosage or 'standard dose'}
Additional Notes from Doctor: {notes or 'none'}

Provide your response in strict JSON format with exactly three fields:
1. "purpose": 1 to 2 short sentences explaining what this medicine does in daily life words (avoid complex medical jargon).
2. "side_effects": 2 to 3 common mild side effects to look out for in simple terms.
3. "precautions": What to avoid (e.g., foods, alcohol, timing tips) and safety advice.

Do NOT include markdown backticks or commentary, only raw JSON:
{{
  "purpose": "...",
  "side_effects": "...",
  "precautions": "..."
}}
"""
    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        response_text = response.text.strip()
        # Clean potential markdown fences
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        parsed = json.loads(response_text)
        return {
            "purpose": parsed.get("purpose", ""),
            "side_effects": parsed.get("side_effects", ""),
            "precautions": parsed.get("precautions", ""),
            "disclaimer": DISCLAIMER_TEXT,
            "source": "gemini_ai",
        }
    except Exception as e:
        logger.warning("Error calling Gemini API for medication explanation: %s. Falling back.", str(e))
        return _get_fallback_explanation(name)
