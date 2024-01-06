from __future__ import annotations

import discord
from discord.app_commands import check

import wavelink

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord import Interaction

    from bot import Amaze
    from helper_bot import NotGDKID


def is_logged_in():
    """
    Check to ensure the command-invoking user has in fact authenticated with Amaze.
    """

    async def predicate(interaction: Interaction) -> bool:
        client: Amaze = interaction.client  # type: ignore
        user_id: int = interaction.user.id

        q = """SELECT credentials FROM authorized
                WHERE user_id = $1
            """
        interaction.extras["credentials"] = await client.db.fetchval(q, user_id)
        return interaction.extras["credentials"] is not None

    return check(predicate)


def is_owner():
    """
    Check to ensure the command-invoking user is the owner of the bot
    """

    async def predicate(interaction: Interaction) -> bool:
        client: NotGDKID = interaction.client  # type: ignore
        user_id: int = interaction.user.id

        return user_id in client.owner_ids

    return check(predicate)


def voice_connected(*, owner_bypass: bool = False):
    """
    Check to ensure the command-invoking user is properly connected to voice

    Arguments
    ---------
    owner_bypass: `bool`
        Whether bot owners are allowed to bypass this check
    """

    async def predicate(interaction: Interaction) -> bool:
        assert (
            interaction.guild
            and interaction.channel
            and isinstance(interaction.user, discord.Member)
            and isinstance(interaction.client, NotGDKID)
            and interaction.user.voice
            and interaction.user.voice.channel
            and interaction.command
        )

        if interaction.user.id in interaction.client.owner_ids and owner_bypass:
            return True

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("join a voice channel first", ephemeral=True)
            return False

        voice = interaction.guild.voice_client
        if not voice:
            if interaction.command.name not in ("play", "join"):
                await interaction.response.send_message("im not in a voice channel", ephemeral=True)
                return False

            permissions = interaction.user.voice.channel.permissions_for(interaction.guild.me)

            if not permissions.connect or not permissions.speak:
                await interaction.response.send_message("im missing connect and/or permissions", ephemeral=True)
                return False

            if not interaction.guild.voice_client:
                await interaction.user.voice.channel.connect(cls=wavelink.Player)  # type: ignore
        else:
            assert isinstance(voice.channel, discord.VoiceChannel)
            if voice.channel.id != interaction.user.voice.channel.id:
                await interaction.response.send_message("we need to be in the same voice channel", ephemeral=True)
                return False

        return True

    return check(predicate)
