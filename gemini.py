import json
import logging
import os

from google import genai
from google.genai import types
from pydantic import BaseModel


# IMPORTANT: KEEP THIS COMMENT
# Follow these instructions when using this blueprint:
# - Note that the newest Gemini model series is "gemini-2.5-flash" or gemini-2.5-pro"
#   - do not change this unless explicitly requested by the user
# - Sometimes the google genai SDK has occasional type errors. You might need to run to validate, at time.  
# The SDK was recently renamed from google-generativeai to google-genai. This file reflects the new name and the new APIs.

# This API key is from Gemini Developer API Key, not vertex AI API Key
client = genai.Client(api_key="AIzaSyB32kRLOKH9QaJtv-Obg0TXIO1lRZD3UoE")


def summarize_article(text: str) -> str:
    prompt = f"Please summarize the following text concisely while maintaining key points:\n\n{text}"

    response = client.models.generate_content(model="gemini-2.5-flash",
                                              contents=prompt)

    return response.text or "SOMETHING WENT WRONG"


class Sentiment(BaseModel):
    rating: int
    confidence: float


def analyze_sentiment(text: str) -> Sentiment:
    try:
        system_prompt = (
            "You are a communication analysis expert for the Shakespeare Club Communication App. "
            "Analyze the communication quality of the text and provide a rating "
            "from 1 to 5 stars and a confidence score between 0 and 1. "
            "Consider clarity, grammar, expression, and communication effectiveness. "
            "Respond with JSON in this format: "
            "{'rating': number, 'confidence': number}")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[
                types.Content(role="user", parts=[types.Part(text=text)])
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=Sentiment,
            ),
        )

        raw_json = response.text
        logging.info(f"Raw JSON: {raw_json}")

        if raw_json:
            data = json.loads(raw_json)
            return Sentiment(**data)
        else:
            raise ValueError("Empty response from model")

    except Exception as e:
        raise Exception(f"Failed to analyze sentiment: {e}")


def analyze_communication_practice(text: str, practice_type: str) -> str:
    """Analyze communication practice submission using Gemini AI"""
    try:
        prompt = f"""
        As an expert in communication analysis for the Shakespeare Club Communication App,
        analyze this {practice_type} practice submission:

        {text}

        Provide detailed feedback focusing on:
        1. Communication clarity and effectiveness
        2. Grammar and language usage
        3. Expression and articulation
        4. Specific areas for improvement
        5. Strengths demonstrated

        Give a comprehensive analysis that will help the student improve their communication skills.
        """

        response = client.models.generate_content(model="gemini-2.5-flash",
                                                  contents=prompt)

        return response.text or "Analysis could not be completed"

    except Exception as e:
        return f"Error in communication analysis: {str(e)}"