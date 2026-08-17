from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

title = "V VALANCH Mens Polo Shirts Short Sleeve Moisture Wicking Golf Polo Athletic Collared Shirt Tennis T-Shirt Tops"

response = client.models.generate_content(
    model="gemini-3.1-flash-lite",
    contents=f"""
Aşağıdaki ürün başlığını doğal ve profesyonel Türkçe e-ticaret diline çevir.

Ürün:
{title}

Sadece Türkçe başlığı döndür.
"""
)

print(response.text)