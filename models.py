
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

print("\nModels available to your Gemini API key:\n")

try:
    for model in client.models.list():
        print(f"Name: {model.name}")
        print(f"Display name: {model.display_name}")
        print(f"Supported actions: {model.supported_actions}")
        print("-" * 50)

except Exception as e:
    print(f"Failed to list models: {type(e).__name__}: {e}")
