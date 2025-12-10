from openai import OpenAI
from app.core.config import settings


def get_openai_client() -> OpenAI:
    """Return a shared OpenAI client configured from settings."""
    return OpenAI(api_key=settings.openai_api_key)


client = get_openai_client()

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
