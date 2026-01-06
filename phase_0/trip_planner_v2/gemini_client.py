from google import genai
import json
import config

class GeminiClient:
    def __init__(self):
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)

    def search_places(self, user_input, city_context=None):
        """
        Asks Gemini to suggest places based on user input.
        """
        prompt = f"""
        Act as a travel expert. The user is interested in visiting places with the following description:
        "{user_input}"
        
        {f"The trip is focused on the city/area of: {city_context}" if city_context else "Identify the likely city or region based on the request, or suggest a general list if no specific location is implied."}

        Please suggest 5-7 specific, real locations that match this description.
        For each location, provide:
        1. Name (official name used in maps)
        2. City/Region
        3. A short reason why it fits the user's request.
        4. Estimated time to spend there (in minutes).

        Output ONLY valid JSON in the following format:
        {{
            "suggested_city": "City Name (if applicable)",
            "places": [
                {{
                    "name": "Place Name",
                    "city": "City Name",
                    "reason": "Reason...",
                    "estimated_duration_minutes": 60
                }}
            ]
        }}
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=prompt
            )
            # Clean up potential markdown formatting
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text)
        except Exception as e:
            print(f"Error querying Gemini: {e}")
            return None
