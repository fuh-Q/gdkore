import re
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

class BotEmojis:
    """
    Config class containing emojis
    """

    YES = "<:_:970213925637484546>"
    NO = "<:_:970214651784736818>"
    BLANK = "<:_:864555461886214174>"
    
    LOADING = "<a:_:937145488493379614>"

    RED_WARNING = "<:_:1026659704979603526>"

    DRIVE = "<:_:1026666226312822824>"
    FORMS = "<:_:1026665895973638235>"
    LINK = "<:_:1026665098242179153>"
    YOUTUBE = "<:_:1026666483830505592>"

    HEHEBOI = "<:_:953811490304061440>"
    HAHALOL = "<a:_:953811854201868340>"
    LUL = "<:_:847113460160004116>"
    PEACE = "<a:_:951323779756326912>"
