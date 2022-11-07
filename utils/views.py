from __future__ import annotations

import random
from typing import List, TYPE_CHECKING

from . import CHOICES

import discord
from discord import Interaction, InteractionMessage, Member, User
from discord.ui import (
    View as DPYView,
    Item,
    Button,
    Select,
    button
)

from google.auth.exceptions import RefreshError

if TYPE_CHECKING:
    from bot import GClass


class Confirm(DPYView):
    """
    Pre-defined `View` class used to prompt the user for a yes/no confirmation.

    Arguments
    ---------
    owner: `User`
        The user being prompted. They will be the one in control of this menu.
    default: `Optional[bool]`
        The default choice in case the view times out (False by default).
    add_third: `Optional[bool]`
        Whether to add a third option for whatever need that might be (False by default).
    yes_label: `Optional[str]`
        Custom label for the accepting button.
    no_label: `Optional[str]`
        Custom label for the rejecting button.
    third_label: `Optional[str]`
        Custom lavel for the third button, if any.

    Parameters
    ----------
    choice: `bool`
        The choice that the user picked.
    interaction: `Interaction`
        The (unresponded) `Interaction` object from the user's button click.
    """

    interaction: Interaction
    original_message: discord.WebhookMessage | InteractionMessage
    children: List[Button | Select]

    def __init__(
        self,
        owner: User | Member,
        *,
        timeout: int = 120,
        default: bool = False,
        add_third: bool = False,
        yes_label: str | None = None,
        no_label: str | None = None,
        third_label: str | None = None,
    ):
        super().__init__(timeout=timeout)

        self.choice = default
        self.owner = owner

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
        self.disable_all()

        try:
            await self.original_message.edit(view=self)

        except discord.HTTPException:
            pass

    def disable_all(self) -> None:
        for c in self.children:
            c.disabled = True

    def _callback(self, interaction: Interaction, btn: Button):
        self.disable_all()

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


class View(DPYView):
    """
    A subclass of `View` that reworks the timeout logic.
    """

    TIMEOUT = 180

    client: GClass
    original_message: discord.Message | discord.WebhookMessage | InteractionMessage
    children: List[Button | Select]

    @property
    def weights(self):
        """
        It's no longer private now >:D
        """
        return self.__weights

    async def _scheduled_task(self, item: Item, interaction: Interaction):
        try:
            item._refresh_state(interaction, interaction.data) # type: ignore

            allow = await self.interaction_check(interaction, item)
            if allow is False:
                return

            if allow is not None:
                self._refresh_timeout()

            if item._provided_custom_id:
                await interaction.response.defer()

            if item.callback is not None:
                await item.callback(interaction)
                if not interaction.response.is_done():
                    await interaction.response.defer()

            await self.after_callback(interaction, item)
        except Exception as e:
            return await self.on_error(interaction, e, item)

    def disable_all(self, *, exclude_urls = False) -> None:
        for c in self.children:
            if exclude_urls and not getattr(c, "url", False):
                c.disabled = True

    def fill_gaps(self) -> None:
        for index, weight in enumerate(self.__weights.weights):
            if weight and weight < 5:
                for _ in range(5 - weight):
                    self.add_item(Button(label="\u200b", disabled=True, row=index))

    async def interaction_check(self, interaction: Interaction, item: Item) -> bool:
        """
        Check function run whenever a component on this view is dispatched.
        To run the component's callback normally, return `True`.
        To run the callback but not refresh the timeout timer, return `None`.
        To negate the interaction sent, return `False`.

        Parameters
        ----------
        interaction: `Interaction`
            The (unresponded) `Interaction` object from the dispatched item.
        item: `Item`
            The item dispatched.

        Raises
        ------
        `NotImplementedError`
            This method was not configured.
        """

        raise NotImplementedError

    async def after_callback(self, interaction: Interaction, item: Item):
        """
        Method called after a component callback has completed.

        Parameters
        ----------
        interaction: `Interaction`
            The (responded) `Interaction` object from the dispatched item.
        item: `Item`
            The item dispatched.
        """

        return


class BasePages(View):
    """
    ABC for paginators to inherit from.
    """

    TIMEOUT = 180 # default timeout

    _pages: List[discord.Embed] # pages are comprised of embeds
    _interaction: Interaction # typically the initial interaction from the user
    _current: int # current page

    _home: BasePages # homepage
    _parent: bool # currently focused in a "sub-view"

    async def interaction_check(self, interaction: Interaction, item: Item) -> bool:
        if interaction.user.id != self._interaction.user.id:
            await interaction.response.send_message(
                content=random.choice(CHOICES), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        if not self._parent:
            self.disable_all(exclude_urls=True)

            try:
                await self._interaction.edit_original_response(view=self)
            except discord.HTTPException:
                pass # we tried

    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        if isinstance(error, RefreshError):
            return self._home.client.dispatch("app_command_error", interaction, error)

        raise error


    @property
    def client(self) -> GClass:
        """
        Returns the main bot object.
        """

        return self._interaction.client # type: ignore

    @property
    def pages(self) -> List[discord.Embed]:
        """
        Returns a list of the pages of courses associated with the user.
        """

        return self._pages

    @property
    def page_count(self) -> int:
        """
        Returns the amount of pages.
        """

        return len(self._pages)

    @property
    def current_page(self) -> int:
        """
        Returns the index of the current page displayed.
        """

        return self._current

    @property
    def edit_kwargs(self):
        return {
            "embed": self.pages[self.current_page],
            "view": self,
        }

    def update_components(self):
        self.button_start.disabled = (self._current == 0)
        self.button_previous.disabled = (self._current == 0)
        self.button_end.disabled = (self._current == self.page_count - 1)
        self.button_next.disabled = (self._current == self.page_count - 1)

        self.button_current.label = f"{self.current_page + 1} / {self.page_count}"


    async def start(
        self,
        *,
        edit_existing: bool = False,
        interaction: Interaction | None = None,
        content: str | None = None
    ):
        interaction = interaction or self._interaction

        self.update_components()
        kwargs = {
            "content": content,
            "embed": self.pages[self.current_page],
            "view": self,
        }

        if edit_existing:
            method = interaction.response.edit_message \
                    if not interaction.response.is_done() \
                    else interaction.edit_original_response
        else:
            method = interaction.response.send_message \
                    if not interaction.response.is_done() \
                    else interaction.followup.send
            kwargs["ephemeral"] = True

        await method(**kwargs)

        self.original_message = await self._interaction.original_response()

    @button(label="❮❮❮", disabled=True)
    async def button_start(self, interaction: Interaction, button: Button):
        self._current = 0
        self.update_components()
        await interaction.response.edit_message(**self.edit_kwargs)

    @button(label="❮", disabled=True)
    async def button_previous(self, interaction: Interaction, button: Button):
        self._current -= 1
        self.update_components()
        await interaction.response.edit_message(**self.edit_kwargs)

    @button(disabled=True)
    async def button_current(self, interaction: Interaction, button: Button):
        await interaction.response.defer()

    @button(label="❯", disabled=True)
    async def button_next(self, interaction: Interaction, button: Button):
        self._current += 1
        self.update_components()
        await interaction.response.edit_message(**self.edit_kwargs)

    @button(label="❯❯❯", disabled=True)
    async def button_end(self, interaction: Interaction, button: Button):
        self._current = self.page_count - 1
        self.update_components()
        await interaction.response.edit_message(**self.edit_kwargs)
