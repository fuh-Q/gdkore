from discord import Interaction
from discord.app_commands import check

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import GClass


def is_logged_in():
    """
    Check to ensure the command-invoking user has in fact authenticated with GClass.
    """

    async def predicate(interaction: Interaction) -> bool:
        client: GClass = interaction.client  # type: ignore
        user_id: int = interaction.user.id

        q = """SELECT credentials FROM authorized
                WHERE user_id = $1
            """
        interaction.extras["credentials"] = await client.db.fetchval(q, user_id)
        return interaction.extras["credentials"] is not None

    return check(predicate)
