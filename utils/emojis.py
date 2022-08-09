import json
import re
from typing import Any, Dict, Type
from discord import PartialEmoji


class NewEmote(PartialEmoji):
    """
    A subclass of `PartialEmoji` that allows an instance to be created from a name
    """

    @classmethod
    def from_name(cls, name: str):
        emoji_name = re.sub("|<|>", "", name)
        a, name, id = emoji_name.split(":")
        return cls(name=name, id=int(id), animated=bool(a))


def emojiclass(cls: Type[Any]):
    """
    A decorator that takes in a class and fills it with emojis from config
    """
    with open("config/emojis.json", "r") as f:
        emojis: Dict[str, str] = json.load(f)

    for k, v in emojis.items():
        setattr(cls, k, v)

    return cls


@emojiclass
class BotEmojis:
    """
    Config class containing emojis
    """

