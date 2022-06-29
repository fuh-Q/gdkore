from __future__ import annotations

import random
import re
import traceback
from typing import Dict, List

import discord
from discord import Interaction, ui
from discord.app_commands import checks, command, describe, errors
from discord.ext import commands

from bot import NotGDKID
from config.utils import (BaseGameView, BotEmojis, Confirm,
                          MaxConcurrencyReached)

NAUGHTY_WORDS = re.compile(r"nigg|bitch|fuck|shit|cock|cunt|retard")


class HangmanLogic:
    def __init__(self, word: str) -> None:
        self.word = word

        self.correct_guesses: List[str] = []
        self.bad_guesses: List[str] = []

    def guess(self, char: str) -> None:
        if char not in self.word:
            self.bad_guesses.append(char)

        else:
            self.correct_guesses.append(char)

    @property
    def lost(self) -> bool:
        return len(self.bad_guesses) >= 8

    @property
    def won(self) -> bool:
        return "◯" not in self.header

    @property
    def header(self) -> str:
        header = "◯" * len(self.word)

        if not self.correct_guesses:
            return header

        for o in enumerate(li := list(self.word)):
            i, char = o

            if char in self.correct_guesses:
                li[i] = char
            else:
                li[i] = "◯"

        header = "".join(li)

        return header

    @property
    def diagram(self) -> str:
        parts = ["😳", [" |", "-|", "-|-"], ["/", "/ \\"]]

        base = "\n".join(
            [
                "```",
                "  ------",
                "  |    |",
                "  |   {0}",
                "  |   {1}",
                "  |   {2}",
                "  |",
                "-----------",
                "```",
            ]
        )

        fmt = ["", "", ""]
        if self.bad_guesses:
            if (le := len(self.bad_guesses)) == 1:
                return "```%s-----------```" % ("\u200b\n" * 7)
            elif le == 2:
                return base.format(*fmt)

            fmt[0] = parts[0]

            if le >= 7:
                fmt[1] = parts[1][2]

                fmt[2] = parts[2][le - 7]

            elif le >= 4:
                fmt[1] = parts[1][le - 4]

            return base.format(*fmt)

        return "```%s```" % ("ㅤㅤㅤㅤㅤㅤ\n" * 7)


class Forfeit(ui.Button):
    view: Hangman

    def __init__(self) -> None:
        super().__init__(emoji=BotEmojis.QUIT_GAME, style=discord.ButtonStyle.danger)

    async def callback(self, interaction: Interaction) -> None:
        view = Confirm(interaction.user)
        embed = discord.Embed(
            title="are you sure you want to forfeit?",
            colour=0xC0382B,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.original_message = await interaction.original_message()

        await view.wait()

        await view.interaction.response.edit_message(view=view)
        if not view.choice:
            return await view.interaction.followup.send("kden", ephemeral=True)

        if not self.view.is_finished():
            self.view.disable_all()

            guesses = sorted(
                self.view.logic.correct_guesses + self.view.logic.bad_guesses
            )
            embed = discord.Embed(
                title=self.view.logic.header, description=self.view.logic.diagram
            ).add_field(name="guesses", value=", ".join(guesses))

            await self.view.original_message.edit(
                content="kbai", embed=embed, view=self.view
            )

            return self.view.stop()


class HangmanModal(ui.Modal, title="guess letter"):
    guess = ui.TextInput(label="guess", placeholder="enter something...", max_length=1)

    def __init__(self, view: Hangman, *args, **kwargs) -> None:
        self.view = view

        super().__init__(*args, **kwargs)

    async def on_submit(self, interaction: Interaction) -> None:
        if (
            self.guess.value in self.view.logic.correct_guesses
            or self.guess.value in self.view.logic.bad_guesses
        ):
            return await interaction.response.send_message(
                "you already guessed that", ephemeral=True
            )

        self.view.logic.guess(self.guess.value)

        guesses = sorted(self.view.logic.correct_guesses + self.view.logic.bad_guesses)
        embed = discord.Embed(
            title=self.view.logic.header, description=self.view.logic.diagram
        ).add_field(name="guesses", value=", ".join(guesses), inline=False)

        top = ""
        if self.view.logic.lost:
            embed.add_field(
                name="btw the word was", value=f"`{self.view.logic.word}`", inline=False
            )

            top = f"{self.view.player.mention} you lose. imagine losing"
            self.view.disable_all()
            self.view.stop()
        elif self.view.logic.won:
            top = f"{self.view.player.mention} ggs"
            self.view.disable_all()
            self.view.stop()

        await interaction.response.edit_message(
            content=top, embed=embed, view=self.view
        )


class Hangman(BaseGameView):
    def __init__(
        self,
        word: str,
        player: discord.User,
        client: NotGDKID,
    ):
        self.logic = HangmanLogic(word)
        self.player = player
        self.client = client
        self.original_message: discord.Message = None

        super().__init__(timeout=120)

        self.client._hangman_games.append(self)

        self.add_item(ui.Button(label="\u200b", disabled=True))
        self.add_item(Forfeit())

    def stop(self) -> None:
        self.client._hangman_games.remove(self)

        return super().stop()

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("its not your game", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.disable_all()

        guesses = sorted(self.view.logic.correct_guesses + self.view.logic.bad_guesses)
        embed = discord.Embed(
            title=self.logic.header, description=self.view.logic.diagram
        ).add_field(name="guesses", value=", ".join(guesses), inline=False)

        top = f"{self.player.mention} ok ig you just {BotEmojis.PEACE}'d out on me\n\n"

        await self.original_message.edit(content=top, embed=embed, view=self)
        self.stop()

    @ui.button(label="make a guess")
    async def guess(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.send_modal(HangmanModal(self))
        return


class Words(commands.Cog):
    def __init__(self, client: NotGDKID) -> None:
        self.client = client

    async def random_word(self, **params) -> str:
        url = "https://random-word-api.herokuapp.com/word"

        if params:
            url += "?"

            for k, v in params.items():
                url += f"{k}={v}&"

        async with self.client.http._HTTPClient__session.get(url.strip("&")) as req:
            word: str = (await req.json())[0]

        return word

    @commands.Cog.listener()
    async def on_ready(self):
        print("Words cog loaded")

    @command(name="hangman")
    async def hangman(self, interaction: Interaction):
        """play hangman"""

        for game in self.client._hangman_games:
            game: Hangman
            if interaction.user == game.player:
                raise MaxConcurrencyReached(game.original_message.jump_url)

        while NAUGHTY_WORDS.search(word := await self.random_word()) is not None:
            word = await self.random_word()

        game = Hangman(word, interaction.user, self.client)

        embed = discord.Embed(title=game.logic.header, description=game.logic.diagram)

        await interaction.response.send_message(
            embed=embed,
            view=game,
        )

        setattr(
            game,
            "original_message",
            await interaction.channel.fetch_message(
                (await interaction.original_message()).id
            ),
        )

        await game.wait()

    @hangman.error
    async def hangman_error(self, interaction: Interaction, error):
        print("".join(traceback.format_exc()))
        if isinstance(error, MaxConcurrencyReached):
            author_game = error.jump_url

            return await interaction.response.send_message(
                "you already have a game going on" f"\n[jump to game](<{author_game}>)",
                ephemeral=True,
            )


async def setup(client: NotGDKID):
    await client.add_cog(Words(client=client))
