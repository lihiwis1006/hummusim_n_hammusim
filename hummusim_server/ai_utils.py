import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_ai_password():
    messages : list = [
        {"role": "system", "content": "You are a secure password generator. Return ONLY the password."},
        {"role": "user", "content": "Generate an 8-character secure password (uppercase, lowercase, digits, symbols)."}
    ]
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=20
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return "TempP@ssw0rd!" # גיבוי למקרה שה-API נופל