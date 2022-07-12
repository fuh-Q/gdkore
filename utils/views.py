from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import CHOICES

import discord
from discord import ui, User, Interaction, InteractionMessage
from discord.ui import Item, View, Button, button
from discord.ui.view import _ViewWeights

if TYPE_CHECKING:
    from bot import Amaze


class Confirm(View):
    """
    Pre-defined `View` class used to prompt the user for a yes/no confirmation

    Arguments
    ---------
    owner: `User`
        The user being prompted. They will be the one in control of this menu
    default: `Optional[bool]`
        The default choice in case the view times out (False by default)
    add_third: `Optional[bool]`
        Whether to add a third option for whatever need that might be (False by default)
    yes_label: `Optional[str]`
        Custom label for the accepting button
    no_label: `Optional[str]`
        Custom label for the rejecting button
    third_label: `Optional[str]`
        Custom lavel for the third button, if any

    Attributes
    ----------
    choice: `bool`
        The choice that the user picked.
    interaction: `Interaction`
        The (unresponded) `Interaction` object from the user's button click.
    """

    def __init__(
        self,
        owner: User,
        *,
        default: bool = False,
        add_third: bool = False,
        yes_label: str = None,
        no_label: str = None,
        third_label: str = None,
    ):
        super().__init__(timeout=120)
        
        self.choice = default
        self.interaction: Interaction = None
        self.owner = owner
        self.original_message: InteractionMessage = None
        
        self.ye.label = yes_label or "ye"
        self.nu.label = no_label or "nu"
        
        if add_third:
            self.third.label = third_label or "..."
        else:
            self.remove_item(self.third)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.owner:
            await interaction.response.send_message(
                content=random.choice(CHOICES), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True

        try:
            await self.original_message.edit(view=self)

        except discord.HTTPException:
            pass
    
    def disable_all(self) -> None:
        for c in self.children:
            c.disabled = True
    
    def _callback(self, interaction: Interaction, btn: Button):
        for c in self.children:
            c.disabled = True
        
        btn.style = discord.ButtonStyle.success
        self.interaction = interaction
        return self.stop()

    @button()
    async def ye(self, interaction: Interaction, btn: Button):
        self.choice = True
        return self._callback(interaction, btn)

    @button()
    async def nu(self, interaction: Interaction, btn: Button):
        self.choice = False
        return self._callback(interaction, btn)

    @button()
    async def third(self, interaction: Interaction, btn: Button):
        self.choice = None
        return self._callback(interaction, btn)


class GameView(View):
    """
    A subclass of `View` that reworks the timeout logic
    """

    client: Amaze = None
    original_message: discord.Message = None
    _View__weights: _ViewWeights

    async def _scheduled_task(self, item: Item, interaction: Interaction):
        try:
            allow = await self.interaction_check(interaction, item)
            if allow is False:
                return

            if allow is not None:
                self._refresh_timeout()

            if item._provided_custom_id:
                await interaction.response.defer()

            await item.callback(interaction)
            if not interaction.response._responded:
                await interaction.response.defer()
        except Exception as e:
            return await self.on_error(e, item, interaction)

    def disable_all(self) -> None:
        for c in self.children:
            c.disabled = True
    
    def fill_gaps(self) -> None:
        for index, weight in enumerate(self._View__weights.weights):
            if weight and weight < 5:
                for _ in range(5 - weight):
                    self.add_item(Button(label="\u200b", disabled=True, row=index))

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        raise NotImplementedError
