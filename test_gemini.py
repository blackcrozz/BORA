from dotenv import load_dotenv
load_dotenv()
from google import genai
import os

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
r = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents="Say OK")
print("✓ Gemini OK:", r.text.strip())