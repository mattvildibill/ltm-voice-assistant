import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env variables
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_daily_prompt():
    prompt = """
    You are a personal historian for a user's life story project.
    Generate a question that helps them reflect on:
    - childhood
    - major life events
    - relationships
    - personal growth
    - values or big lessons

    The question should be:
    - specific
    - emotional or thoughtful
    - short (1 sentence)
    - easy to answer via voice
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content
