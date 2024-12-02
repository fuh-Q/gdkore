from __future__ import annotations

import random
from typing import List, TYPE_CHECKING

from . import CHOICES

import discord
from discord import Interaction, InteractionMessage, Member, User
from discord.ui import View as DPYView, Item, Button, Select, button

from google.auth.exceptions import RefreshError

if TYPE_CHECKING:
    from discord.ext.commands import Context

    from bot import Amaze
    from helper_bot import NotGDKID


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

    Attributes
    ----------
    choice: `bool`
        The choice that the user picked.
    interaction: `Interaction`
        The (unresponded) `Interaction` object from the user's button click.
    """

    interaction: Interaction
    original_message: discord.WebhookMessage | InteractionMessage | discord.Message
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

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if interaction.user != self.owner:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
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

    client: Amaze
    original_message: discord.Message | discord.WebhookMessage | InteractionMessage
    children: List[Button | Select]
    __discord_auto_defer__: bool

    @property
    def weights(self):
        """
        It's no longer private now >:D
        """
        return self.__weights

    @property
    def auto_defer(self) -> bool:
        """
        Whether we will defer interactions should they not complete in the dispatched item's callback.
        """
        return self.__discord_auto_defer__

    def __init_subclass__(cls, *, auto_defer: bool) -> None:
        cls.__discord_auto_defer__ = auto_defer
        return super().__init_subclass__()

    async def _scheduled_task(self, item: Item, interaction: Interaction):
        try:
            item._refresh_state(interaction, interaction.data)  # type: ignore

            allow = await self.interaction_check(interaction, item)
            if allow is False:
                return

            if allow is not None:
                self._refresh_timeout()

            if item.callback is not None:
                await item.callback(interaction)
                if not interaction.response.is_done() and self.auto_defer:
                    await interaction.response.defer()

            await self.after_callback(interaction, item)
        except Exception as e:
            return await self.on_error(interaction, e, item)

    def disable_all(self, *, exclude_urls=False) -> None:
        for c in self.children:
            if exclude_urls and not getattr(c, "url", None) or not exclude_urls:
                c.disabled = True

    def reposition(self, item: Item) -> None:
        self.remove_item(item)
        self.add_item(item)

    def fill_gaps(self) -> None:
        for index, weight in enumerate(self.__weights.weights):
            if weight and weight < 5:
                for _ in range(5 - weight):
                    self.add_item(Button(label="\u200b", disabled=True, row=index))

    async def interaction_check(self, interaction: Interaction, item: Item) -> bool | None:
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

        If the `auto_defer` keyword has been set to `True` in the subclass definition,
        the interaction object passed will have been deferred at this point.

        Parameters
        ----------
        interaction: `Interaction`
            The `Interaction` object from the dispatched item.
        item: `Item`
            The item dispatched.
        """

        return


class BasePages(View, auto_defer=True):
    """
    ABC for paginators to inherit from.
    """

    TIMEOUT = 180  # default timeout

    _current: int = 0  # current page
    _pages: List[discord.Embed] = []  # pages are comprised of embeds
    _interaction: Interaction  # typically the initial interaction from the user
    _ctx: Context[Amaze | NotGDKID] | None = None  # instance of context if this is being used in a prefixed command

    _home: BasePages  # homepage
    _parent: bool = False  # currently focused in a "sub-view"

    async def interaction_check(self, interaction: Interaction, item: Item) -> bool:
        uid = self._ctx.author.id if self._ctx else self._interaction.user.id

        if interaction.user.id != uid:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self._parent:
            return

        self.disable_all(exclude_urls=True)

        method = self.original_message.edit if self._ctx else self._interaction.edit_original_response

        try:
            await method(view=self)
        except discord.HTTPException:
            pass  # we tried

    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        if isinstance(error, RefreshError):
            return self._home.client.dispatch("app_command_error", interaction, error)

        raise error

    @property
    def client(self) -> Amaze | NotGDKID:
        """
        Returns the main bot object.
        """

        if self._ctx:
            return self._ctx.bot

        return self._interaction.client  # type: ignore

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
        self.button_start.disabled = self._current == 0
        self.button_previous.disabled = self._current == 0
        self.button_end.disabled = self._current == self.page_count - 1
        self.button_next.disabled = self._current == self.page_count - 1

        self.button_current.label = f"{self.current_page + 1} / {self.page_count}"

    async def start(
        self,
        *,
        ephemeral: bool = True,
        edit_existing: bool = False,
        interaction: Interaction | None = None,
        content: str | None = None,
    ):
        if not interaction and not hasattr(self, "_interaction"):
            raise TypeError("Interaction must be set")

        interaction = interaction or self._interaction

        self.update_components()
        kwargs = {
            "content": content,
            "embed": self.pages[self.current_page],
            "view": self,
        }

        if edit_existing:
            method = (
                interaction.response.edit_message
                if not interaction.response.is_done()
                else interaction.edit_original_response
            )
        else:
            method = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send
            kwargs["ephemeral"] = ephemeral

        await method(**kwargs)

        self.original_message = await self._interaction.original_response()

    @button(label="❮❮❮", disabled=True, row=0)
    async def button_start(self, interaction: Interaction, button: Button):
        self._current = 0

    @button(label="❮", disabled=True, row=0)
    async def button_previous(self, interaction: Interaction, button: Button):
        self._current -= 1

    @button(disabled=True, row=0)
    async def button_current(self, interaction: Interaction, button: Button):
        await interaction.response.defer()

    @button(label="❯", disabled=True, row=0)
    async def button_next(self, interaction: Interaction, button: Button):
        self._current += 1

    @button(label="❯❯❯", disabled=True, row=0)
    async def button_end(self, interaction: Interaction, button: Button):
        self._current = self.page_count - 1
