import os
import requests
from dotenv import load_dotenv
load_dotenv()
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_core.tools import tool
from langsmith import traceable

llm = init_chat_model(
    "openai/gpt-oss-120b",
    model_provider="openai",
    base_url="https://openrouter.ai/api/v1",
    temperature=0.6,
)

# ---------- Tools ----------
# 3. Define the weather tool
@tool
def get_weather(city: str) -> dict:
    """Get current weather and a 3-day forecast for any city."""

    geo_url = "https://geocoding-api.open-meteo.com/v1/search"

    geo_response = requests.get(
        geo_url,
        params={
            "name": city,
            "count": 1,
            "language": "en",
        },
        timeout=15,
    )
    geo_response.raise_for_status()

    locations = geo_response.json().get("results", [])

    if not locations:
        return {"error": f"City not found: {city}"}

    location = locations[0]

    weather_url = "https://api.open-meteo.com/v1/forecast"

    weather_response = requests.get(
        weather_url,
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "apparent_temperature,precipitation,"
                "weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,"
                "temperature_2m_min,precipitation_probability_max"
            ),
            "forecast_days": 3,
            "timezone": "auto",
        },
        timeout=15,
    )
    weather_response.raise_for_status()

    data = weather_response.json()

    return {
        "city": location["name"],
        "country": location.get("country"),
        "current": data.get("current"),
        "daily_forecast": data.get("daily"),
    }

@tool
def get_news(topic: str, max_articles: int = 5) -> dict:
    '''Get the latest news articles about a topic.
    :param topic: what to search news for, e.g. "tesla" or "apple"
    :param max_articles: how many articles to return (default 5)
    :return: dict with a list of articles (title, source, description, url, published date)
    '''
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"error": "NEWS_API_KEY is missing in .env"}

    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": topic,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": max_articles,
                "apiKey": api_key,
            },
            timeout=10,
        )
        data = response.json()
    except Exception as e:
        return {"error": f"Request failed: {e}"}

    if data.get("status") != "ok":
        return {"error": data.get("message", "Unknown error from News API")}

    articles = [
        {
            "title": a.get("title"),
            "source": a.get("source", {}).get("name"),
            "description": a.get("description"),
            "url": a.get("url"),
            "published_at": a.get("publishedAt"),
        }
        for a in data.get("articles", [])
    ]
    return {"topic": topic, "total_results": data.get("totalResults"), "articles": articles}


SYSTEM_PROMPT = (
    "If you need several tools, call ALL of them together in a single response. "
    "Never call tools one by one. For example, if the user asks for weather and news, "
    "request get_weather and get_news in the same step."
)
# 5. Create the agent with the instructions and tool
agent = create_agent(
    model=llm,
    tools=[get_weather, get_news],
    system_prompt=SYSTEM_PROMPT,
)


# 6. Get a response from the agent
@traceable
def getchat(user_input: str):
    response = agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": user_input,
            }
        ]
    })

    return {
        "info": response["messages"][-1].content
    }


# 7. Test
if __name__ == "__main__":
    result = getchat("give me any 1 news in Lahore and What is the current weather in Lahore??")
    print(result["info"])