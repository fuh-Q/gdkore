import io
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Tuple

import aiohttp
import discord
from discord.ext import tasks
from PIL import Image, ImageDraw

from weather_bot import NotGDKID

RT = Mapping[str, Any]
URL = "https://api.weatherapi.com/v1/forecast.json?key=%s&q=Kanata&days=2&alerts=yes&aqi=no"


async def weather_request(key: str) -> Dict[str, Any]:
    async with session.get(URL % key) as res:
        data = await res.json()

    return data


async def icon_request(url: str, resize: int = 5) -> Image.Image:
    async with session.get(url) as res:
        buffer = io.BytesIO(await res.content.read())
        buffer.seek(0)

    img = Image.open(buffer)
    return img.resize((img.width * resize, img.height * resize))


async def current_time(data: RT, img: Image.Image, draw: ImageDraw.ImageDraw):
    string = data["location"]["name"]

    width = NotGDKID.medium_text.getsize(string)[0]
    draw.text(
        (int((img.width - width) / 8), int(img.height / 25)),
        string,
        (255, 255, 255),
        NotGDKID.medium_text,
    )

    string = data["current"]["condition"]["text"]
    width = NotGDKID.normal_text.getsize(string)[0]
    draw.text(
        (int((img.width - width) / 6), int(img.height / 2.15)),
        string,
        (255, 255, 255),
        NotGDKID.normal_text,
    )


async def celsius_deg(data: RT, img: Image.Image, draw: ImageDraw.ImageDraw):
    deg = f"{round(data['current']['temp_c'])}°C"
    width = NotGDKID.thiccc_text.getsize(deg)[0]
    draw.text(
        (int((img.width - width) / 10), int(img.height / 2)),
        deg,
        (59, 200, 93),
        NotGDKID.thiccc_text,
    )

    feels_like = f"Feels like {round(data['current']['feelslike_c'])}°C"
    width = NotGDKID.normal_text.getsize(feels_like)[0]
    draw.text(
        (int((img.width - width) / 7), int(img.height / 1.2)),
        feels_like,
        (255, 255, 255),
        NotGDKID.normal_text,
    )


async def forecast(
    data: RT, img: Image.Image, draw: ImageDraw.ImageDraw, precise: float
):
    tz = timezone(timedelta(hours=-4))
    futures: List[Dict[str, Any] | None] = [
        obj
        for obj in data["forecast"]["forecastday"][0]["hour"]
        if obj["time_epoch"] > precise
    ]
    if len(futures) >= 3:
        futures = futures[:3]
    else:  # spilling into the next day
        futures += [obj for obj in data["forecast"]["forecastday"][1]["hour"]][
            : 3 - len(futures)
        ]

    def maf(w_multi: int, h_multi: int) -> Tuple[int, int]:
        return (
            int((img.width - weather_icon.width) * w_multi),
            int((index + h_multi) * (img.height / (len(futures) + 1))),
        )

    for index, obj in enumerate(futures):
        dt = datetime.fromtimestamp(obj["time_epoch"], tz=tz)
        text = dt.strftime("%I %p").strip("0")
        temperature = f"{round(obj['temp_c'])}°C"

        weather_icon = await icon_request(f"https:{obj['condition']['icon']}", resize=3)
        draw.text(maf(0.6, 0.55), text, (255, 255, 255), NotGDKID.normal_text)
        img.paste(weather_icon, maf(0.6, 0.75), weather_icon)
        draw.text(maf(0.75, 0.65), temperature, (59, 200, 93), NotGDKID.medium_text)
        weather_icon.close()


async def create_image(data: RT) -> discord.File:
    start = time.time()
    img = Image.open("assets/ottawa.png")
    draw = ImageDraw.Draw(img)

    weather_icon = await icon_request(f"https:{data['current']['condition']['icon']}")
    img.paste(
        weather_icon,
        (int((img.width - weather_icon.width) / 6), int(img.height / 5.5)),
        weather_icon,
    )
    weather_icon.close()

    await current_time(data, img, draw)
    await celsius_deg(data, img, draw)
    await forecast(data, img, draw, start)

    buffer = io.BytesIO()
    img.save(buffer, "png")
    img.close()

    buffer.seek(0)
    return discord.File(buffer, "weather.png")


@tasks.loop(minutes=5)
async def weather_task(client: NotGDKID):
    data = await weather_request(client.weather_key)

    file = await create_image(data)
    if hasattr(client, "weather_hook"):
        await client.weather_hook.edit_message(
            client.weather_hook_msg_id, attachments=[file]
        )
    else:
        await client.weather_message.edit(attachments=[file])


async def teardown(_):
    weather_task.cancel()

    if session is not None and not session.closed:
        await session.close()


async def setup(client: NotGDKID):
    global session
    session = aiohttp.ClientSession()

    weather_task.start(client)
    print("Weather task started")
