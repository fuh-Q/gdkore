from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain
from typing import Callable, Dict, List, Tuple, TYPE_CHECKING

import discord
from discord import Webhook
from discord.app_commands import checks, command
from discord.ext import commands, tasks
from discord.http import INTERNAL_API_VERSION
from discord.ui import Button, Select

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, HttpError

from cogs.browser import AttachmentsView, get_due_date, ICONS
from utils import (
    BasePages,
    BotColours,
    CappedDict,
    Confirm,
    Embed,
    PrintColours,
    View,
    cap,
    format_google_time,
    is_logged_in,
)

if TYPE_CHECKING:
    from discord import Interaction
    from discord.ui import Item

    from bot import GClass
    from utils import Attachment, Post, Resource, WebhookData

DEL_QUERY = """DELETE FROM webhooks
                WHERE user_id = $1
                AND course_id = $2
                AND channel_id = $3"""


@dataclass(init=False, slots=True)
class EmbedWithPostData:
    assignment_response: str | None
    embed: Embed
    created_at: datetime
    materials: List[Attachment]
    type: str
    url: str

    def __init__(self, embed: Embed, post: Post):
        self.embed = embed
        self.created_at = format_google_time(post)
        self.materials = post.get("materials", [])
        self.url = post["alternateLink"]
        self.assignment_response = None

        if worktype := post.get("workType", None):
            self.type = "assignment"
            self.assignment_response = worktype.lower().replace("_", " ")
        elif post.get("text", None):
            self.type = "announcement"
        else:
            self.type = "material"

    @property
    def embed_header(self) -> str:
        return self.assignment_response or self.type


@tasks.loop(minutes=10)
async def fetch_posts(client: GClass):
    def run_google() -> Tuple[Post]:  # all google libs are sync
        kwargs = {"courseId": webhook["course_id"], "pageSize": 5}
        start = len(webhook) - 3
        courses: Resource = service.courses()
        _: Callable[[Resource], Dict[str, Post]] = lambda item: item.list(**kwargs).execute()

        # fmt: off
        return tuple(chain.from_iterable(map(lambda i: tuple(filter(
            lambda m: (created_at := format_google_time(m)) > webhook[tuple(webhook.keys())[i[0] + start]]
            and created_at > webhook["last_date"], i[1]
        )), enumerate((
            _(courses.announcements()).get("announcements", []),  # announcements
            _(courses.courseWorkMaterials()).get("courseWorkMaterial", []),  # materials
            _(courses.courseWork()).get("courseWork", []),  # assignments
        )))))
        # fmt: on

    def make_embeds(posts: Tuple[Post]) -> List[EmbedWithPostData]:  # transform post JSON into dpy embeds
        pages: List[EmbedWithPostData] = []

        for post in posts:
            d = post.get("text", "") or post.get("description", "")

            page = Embed(
                title=f"{cap(post.get('title', '')):256}",
                description=f"{cap(d):4096}",
                timestamp=format_google_time(post),
                url=post["alternateLink"],
            ).set_footer(text="posted at", icon_url=ICONS["posted"])

            if post.get("workType", None):
                page.colour = BotColours.purple

            if due_date := get_due_date(post):  # type: ignore
                page.add_field(name="assignment due", value=f"<t:{due_date.timestamp():.0f}:R>")

            assert page.description
            char_count = page.character_count()
            if char_count > 6000:
                page.description = format(cap(page.description), str(4096 - (char_count - 6000)))

            obj = EmbedWithPostData(page, post)
            obj.embed.set_author(name="new " + (n := obj.embed_header), icon_url=ICONS[n], url=post["alternateLink"])
            pages.append(obj)

        return pages

    async def delete_webhook(*, is_deleted: bool = False) -> None:  # delete the current webhook
        assert client.session
        await client.db.execute(DEL_QUERY, webhook["user_id"], webhook["course_id"], webhook["channel_id"])

        if not is_deleted:
            try:
                wh = Webhook.from_url(webhook["url"], session=client.session, bot_token=client.token)
                await wh.send(embed=Embed(description="course not found, deleting this webhook..."))
                await wh.delete(reason=f"associated course could not be found")
            except discord.HTTPException:
                pass  # we tried

    async def post_data(pages: List[EmbedWithPostData]) -> None:  # post embeds to the webhook's channel
        wh: discord.Webhook
        assert client.session

        last_posts = {n: datetime.now(tz=timezone.utc) for n in ("announcement", "material", "assignment")}

        if not webhook["url"]:
            channel = client.get_channel(webhook["channel_id"])
            if not channel:
                return await delete_webhook(is_deleted=True)

            assert isinstance(channel, discord.TextChannel)
            try:
                wh = await channel.create_webhook(
                    name=webhook["course_name"], reason=f"created webhook for course {webhook['course_name']}"
                )
            except discord.HTTPException:
                return await delete_webhook(is_deleted=True)

            q = """UPDATE webhooks SET url = $1
                    WHERE user_id = $2
                    AND course_id = $3
                    AND channel_id = $4
                """
            await client.db.execute(q, wh.url, webhook["user_id"], webhook["course_id"], webhook["channel_id"])
        else:
            wh = Webhook.from_url(webhook["url"], session=client.session)

        for page in pages:
            last_posts[page.type] = page.created_at

            await asyncio.sleep(1)
            view = View()
            view.add_item(Button(label="view in classroom", style=discord.ButtonStyle.link, url=page.url))
            view.weights.weights[0] = 5
            AttachmentsView.add_attachments(page.materials, view)

            async with client.session.post(
                url=f"https://discord.com/api/v{INTERNAL_API_VERSION}/webhooks/{wh.id}/{wh.token}",
                json={
                    "username": webhook["course_name"],
                    "embeds": [page.embed.to_dict()],
                    "components": view.to_components(),
                },
            ) as resp:
                if resp.status in (401, 403, 404):
                    await delete_webhook()

        q = """UPDATE webhooks SET
                    last_date = $4,
                    last_announcement_post = $5,
                    last_material_post = $6,
                    last_assignment_post = $7
                WHERE user_id = $1
                AND course_id = $2
                AND channel_id = $3
            """
        await client.db.execute(
            q,
            webhook["user_id"],
            webhook["course_id"],
            webhook["channel_id"],
            datetime.now(tz=timezone.utc),
            *last_posts.values(),
        )

    resource_cache: CappedDict[int, Resource] = CappedDict(50)
    post_cache: CappedDict[int, Tuple[Post]] = CappedDict(100)
    webhooks: List[WebhookData] = await client.db.fetch("SELECT * FROM webhooks")

    client.logger.info(
        "%srunning loop for %s%s%s webhook(s)",
        PrintColours.BLUE,
        PrintColours.GREEN,
        format(len(webhooks), ","),
        PrintColours.BLUE,
    )

    for webhook in webhooks:
        await asyncio.sleep(0.1)

        if not (service := resource_cache.get(webhook["user_id"], None)):
            q = """SELECT credentials FROM authorized
                    WHERE user_id = $1
                """
            creds = Credentials.from_authorized_user_info(await client.db.fetchval(q, webhook["user_id"]))
            service: Resource = build("classroom", "v1", credentials=creds)
            resource_cache[webhook["user_id"]] = service

        try:
            if (new_posts := post_cache.get(webhook["course_id"], None)) is None:
                if not (new_posts := await asyncio.to_thread(run_google)):
                    post_cache[webhook["course_id"]] = tuple()
                    continue

                new_posts = tuple(sorted(new_posts, key=lambda i: format_google_time(i).timestamp()))
                post_cache[webhook["course_id"]] = new_posts
            elif not new_posts:
                continue

            await post_data(make_embeds(new_posts))

        except RefreshError:
            await delete_webhook()
            await client.remove_access(webhook["user_id"])
        except HttpError as e:
            if e.status_code in (401, 403, 404):
                await delete_webhook()


class WebhookPicker(Select):
    _view: WebhookPages

    @property
    def view(self) -> WebhookPages:
        return self._view

    def __init__(self, view: WebhookPages) -> None:
        self._view = view

        super().__init__(placeholder=self.get_placeholder(), min_values=1, max_values=1, options=self.view.select_options)

    def get_placeholder(self) -> str:
        total = len(tuple(chain.from_iterable(self.view._webhooks)))
        if not total:
            return f"remove a webhook... [0-0 of 0]"

        if total > self.view.WEBHOOKS_PER_PAGE:
            start = self.view.WEBHOOKS_PER_PAGE * self.view.current_page + 1
            stop = start + len(self.view._webhooks[self.view.slice_index]) - 1
        else:
            start = 1
            stop = total

        return f"{cap(f'remove a webhook... [{start}-{stop} of {total}]'):150}"

    async def callback(self, interaction: Interaction) -> None:
        assert self.view.client.session
        await interaction.response.defer(ephemeral=True)
        view = Confirm(interaction.user)

        wh: WebhookData = self.view._webhooks[self.view.current_page].pop(idx := int(self.values[0]))
        embed = Embed(
            title="confirm delete webhook",
            description=f"are you sure you want to delete the webhook for "
            f"**{cap(wh['course_name']):256}** created in <#{wh['channel_id']}>?",
            colour=BotColours.red,
        )
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.original_message = msg

        expired = await view.wait()
        if expired:
            return

        await view.interaction.response.defer()
        await interaction.followup.delete_message(msg.id)
        if not view.choice:
            return

        if wh["url"]:
            try:
                await Webhook.from_url(wh["url"], session=self.view.client.session, bot_token=self.view.client.token).delete(
                    reason=f"{interaction.user.name} ({interaction.user.id}) deleted webhook"
                )
            except discord.NotFound:
                pass  # meh their problem now

        await self.view.client.db.execute(DEL_QUERY, wh["user_id"], wh["course_id"], wh["channel_id"])

        self.view._pages[self.view.current_page].remove_field(idx)
        self.placeholder = self.get_placeholder()
        if new_options := self.view.select_options:
            self.options = new_options
        else:
            self.disabled = True

        await interaction.edit_original_response(**self.view.edit_kwargs)


class WebhookPages(BasePages, auto_defer=False):
    WEBHOOKS_PER_PAGE = 12

    def __init__(self, interaction: Interaction, webhooks: List[WebhookData]):
        self._interaction = interaction

        self._webhooks: List[List[WebhookData]] = []

        self.webhooks_to_pages(webhooks=webhooks)

        super().__init__(timeout=self.TIMEOUT)

        self.select_menu = WebhookPicker(self)
        self.add_item(self.select_menu)

    @property
    def slice_index(self) -> int:
        nslices = len(self._webhooks)
        return self.current_page if self.current_page <= nslices - 1 else nslices - 1

    def webhooks_to_pages(self, *, webhooks: List[WebhookData]):
        interaction = self._interaction

        while webhooks != []:
            page = Embed()
            page.set_author(
                name=f"{interaction.user.name}#{interaction.user.discriminator}'s webhooks",
                icon_url=interaction.user.display_avatar.url,
            )
            self._webhooks.append(bundle := webhooks[: self.WEBHOOKS_PER_PAGE])
            for webhook in bundle:
                page.add_field(
                    name=f"{cap(webhook['course_name']):256}",
                    value=f"— created in <#{webhook['channel_id']}>\n"
                    f"— in guild `{self.client.get_guild(webhook['guild_id']).name}`",
                )
            self._pages.append(page)
            webhooks = webhooks[self.WEBHOOKS_PER_PAGE :]

    @property
    def select_options(self):
        return [
            discord.SelectOption(
                label=w["course_name"],
                value=str(idx),
            )
            for idx, w in enumerate(self._webhooks[self.current_page])
        ]

    async def after_callback(self, interaction: Interaction, item: Item):
        self.update_components()
        if new_options := self.select_options:
            self.select_menu.disabled = False
            self.select_menu.options = new_options

            self.select_menu.placeholder = self.select_menu.get_placeholder()
        else:
            self.select_menu.placeholder = f"remove a webhook... [0-0 of 0]"
            self.select_menu.disabled = True

        if item is not self.select_menu:
            await interaction.response.edit_message(**self.edit_kwargs)


class Webhooks(commands.Cog):
    def __init__(self, client: GClass) -> None:
        self.client = client

        fetch_posts.before_loop(client.wait_until_ready)
        self.running_task = fetch_posts.start(client)

    async def cog_unload(self) -> None:
        self.running_task.cancel()

    @command(name="webhooks")
    @is_logged_in()
    @checks.cooldown(1, 15)
    async def view_webhooks(self, interaction: Interaction):
        """
        view your configured webhooks
        """

        await interaction.response.defer(ephemeral=True)

        q = """SELECT * FROM webhooks
                WHERE user_id = $1
            """
        webhooks: List[WebhookData] = await self.client.db.fetch(q, interaction.user.id)
        if not webhooks:
            return await interaction.edit_original_response(embed=Embed(description="no webhooks to display"))

        await WebhookPages(interaction, webhooks).start(edit_existing=True)


async def setup(client: GClass):
    await client.add_cog(Webhooks(client=client))
