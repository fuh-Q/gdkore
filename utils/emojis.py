import re
from discord import PartialEmoji


class NewEmote(PartialEmoji):
    """
    A subclass of `PartialEmoji` that allows an instance to be created from a name.
    """

    @classmethod
    def from_name(cls, name: str):
        emoji_name = re.sub("|<|>", "", name)
        a, name, id = emoji_name.split(":")
        return cls(name=name, id=int(id), animated=bool(a))

class BotEmojis:
    """
    Config class containing emojis.
    """

    YES = "<:_:970213925637484546>"
    NO = "<:_:970214651784736818>"
    BLANK = "<:_:864555461886214174>"
    SQ = "<:_:975147379235913738>"
    QUIT_GAME = "<:_:954097284482736128>"

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

    CHECKERS_RED = "<:_:975147416800096276>"
    CHECKERS_BLUE = "<:_:975147395455270932>"
    CHECKERS_RED_KING = "<:_:975147966388113517>"
    CHECKERS_BLUE_KING = "<:_:975147969886171177>"
    CHECKERS_RED_SELECTED = "<a:_:975246608314798130>"
    CHECKERS_BLUE_SELECTED = "<a:_:975236407901687868>"
    CHECKERS_RED_KING_SELECTED = "<a:_:975248465032523807>"
    CHECKERS_BLUE_KING_SELECTED = "<a:_:975248465032523806>"

    CHECKERS_RED_NORTHWEST = "<a:_:975402198156607518>"
    CHECKERS_RED_NORTHEAST = "<a:_:975403366630961222>"
    CHECKERS_RED_SOUTHEAST = "<a:_:975402198181761034>"
    CHECKERS_RED_SOUTHWEST = "<a:_:975403366458982400>"
    CHECKERS_BLUE_NORTHWEST = "<a:_:975403366677086231>"
    CHECKERS_BLUE_NORTHEAST = "<a:_:975403366836469790>"
    CHECKERS_BLUE_SOUTHEAST = "<a:_:975403366769365112>"
    CHECKERS_BLUE_SOUTHWEST = "<a:_:975403366849065080>"
