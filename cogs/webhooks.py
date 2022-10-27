from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain
from typing import Callable, Generic, List, Tuple, TypeVar

import discord
from discord import Webhook, Interaction
from discord.app_commands import command
from discord.ext import commands, tasks
from discord.http import INTERNAL_API_VERSION
from discord.ui import Button, Item, Select

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource, HttpError

from bot import GClass
from cogs.browser import AttachmentsView, get_due_date, ICONS
from utils import (
    Attachment,
    BasePages,
    BotColours,
    Confirm,
    Post,
    PrintColours,
    View,
    WebhookData,
    format_google_time,
    is_logged_in,
)

KT = TypeVar("KT")
VT = TypeVar("VT")

DEL_QUERY = """DELETE FROM webhooks
                WHERE user_id = $1
                AND course_id = $2
                AND channel_id = $3"""

@dataclass(repr=False, eq=False)
class CappedDict(dict, Generic[KT, VT]):
    cap: int
    
    def __setitem__(self, k: KT, v: VT) -> None:
        super().__setitem__(k, v)
        
        if len(self) > self.cap:
            del self[tuple(self)[0]]
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

@dataclass(init=False, slots=True)
class EmbedWithPostData:
    assignment_response: str | None
    embed: discord.Embed
    created_at: datetime
    materials: List[Attachment]
    type: str
    url: str
    
    def __init__(self, embed: discord.Embed, post: Post):
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

@tasks.loop(minutes=15)
async def fetch_posts(client: GClass):
    def run_google() -> Tuple[Post]: # all google libs are sync
        kwargs = {
            "courseId": webhook["course_id"],
            "pageSize": 5
        }
        courses = service.courses()
        _: Callable[[Resource], Post] = lambda item: item.list(**kwargs).execute()
        
        return tuple(chain.from_iterable(map(lambda i: tuple(filter(
            lambda m: (created_at := format_google_time(m)) > webhook[tuple(webhook.keys())[i[0] + 7]]
            and created_at > webhook["last_date"], i[1]
        )), enumerate((
            _(courses.announcements()).get("announcements", []),              # announcements
            _(courses.courseWorkMaterials()).get("courseWorkMaterial", []),   # materials
            _(courses.courseWork()).get("courseWork", [])                     # assignments
        )))))
    
    def make_embeds(posts: Tuple[Post]) -> List[EmbedWithPostData]: # transform post JSON into dpy embeds
        pages: List[EmbedWithPostData] = []
        
        for post in posts:
            t = post.get("title", "")
            d = post.get("text", "") or post.get("description", "")
            
            page = discord.Embed(
                title=t if len(t) <= 256 else t[:253] + "...",
                description=d if len(d) <= 4096 else d[:4093] + "...",
                timestamp=format_google_time(post),
                url=post["alternateLink"]
            ).set_footer(
                text="posted at",
                icon_url=ICONS["posted"]
            )
            
            if post.get("workType", None):
                page.colour = BotColours.purple
            
            if (due_date := get_due_date(post)):
                page.add_field(
                    name="assignment due",
                    value=f"<t:{int(due_date.timestamp())}:R>"
                )
            
            obj = EmbedWithPostData(page, post)
            obj.embed.set_author(
                name="new " + (n := obj.embed_header),
                icon_url=ICONS[n],
                url=post["alternateLink"]
            )
            pages.append(obj)
        
        return pages

    async def delete_webhook() -> None: # delete the current webhook
        await client.db.execute(DEL_QUERY,
            webhook["user_id"],
            webhook["course_id"],
            webhook["channel_id"]
        )
        
        try:
            wh = Webhook.from_url(webhook["url"], session=client.session, bot_token=client.token)
            await wh.send(embed=discord.Embed(
                description="course not found, deleting this webhook..."
            ))
            await wh.delete(reason=f"associated course could not be found")
        except discord.HTTPException:
            pass # we tried
    
    async def post_data(pages: List[EmbedWithPostData]) -> None: # post embeds to the webhook's channel
        args = 0, timezone.utc
        last_posts = {
            "announcement": datetime.fromtimestamp(*args),
            "material": datetime.fromtimestamp(*args),
            "assignment": datetime.fromtimestamp(*args)
        }
        
        for page in pages:
            last_posts[page.type] = page.created_at
            
            await asyncio.sleep(1)
            view = View()
            view.add_item(Button(
                label="view in classroom",
                style=discord.ButtonStyle.link,
                url=page.url
            ))
            view.weights.weights[0] = 5
            AttachmentsView.add_attachments(page.materials, view)
            
            wh = Webhook.from_url(webhook["url"], session=client.session)
            async with client.session.post(
                f"https://discord.com/api/v{INTERNAL_API_VERSION}/webhooks/{wh.id}/{wh.token}",
                json={
                    "username": webhook["course_name"],
                    "embeds": [page.embed.to_dict()],
                    "components": view.to_components()
                }
            ) as resp:
                if resp.status == 404:
                    await delete_webhook()
        
        q = """UPDATE webhooks SET
                    last_date = $2,
                    last_announcement_post = $3,
                    last_material_post = $4,
                    last_assignment_post = $5
                WHERE user_id = $1
            """
        await client.db.execute(q,
            webhook["user_id"],
            datetime.now(tz=timezone.utc),
            *last_posts.values()
        )
    
    webhooks: List[WebhookData] = await client.db.fetch("SELECT * FROM webhooks")
    resource_cache: CappedDict[int, Resource] = CappedDict(25)
    post_cache: CappedDict[int, Tuple[Post]] = CappedDict(50)
    
    client.logger.info(
        PrintColours.BLUE + "running loop for "
        f"{PrintColours.GREEN}{len(webhooks):,}{PrintColours.BLUE} webhook(s)"
    )
    
    for webhook in webhooks:
        await asyncio.sleep(0.1)
        q = """SELECT credentials FROM authorized
                WHERE user_id = $1
            """
        creds = Credentials.from_authorized_user_info(await client.db.fetchval(q, webhook["user_id"]))
        if not (service := resource_cache.get(webhook["user_id"], None)):
            service: Resource = build("classroom", "v1", credentials=creds)
            resource_cache[webhook["user_id"]] = service
        
        try:
            if (new_posts := post_cache.get(webhook["course_id"], None)) is None:
                if not (new_posts := await asyncio.to_thread(run_google)):
                    post_cache[webhook["course_id"]] = tuple()
                    continue
                
                new_posts = tuple(sorted(
                    new_posts,
                    key = lambda i: format_google_time(i).timestamp()
                ))
                post_cache[webhook["course_id"]] = new_posts
            
            if not new_posts:
                continue
            
            await post_data(make_embeds(new_posts))
            
        except RefreshError:
            await delete_webhook()
            await client.remove_access(webhook["user_id"])
        except HttpError as e:
            if e.status_code == 404:
                await delete_webhook()

class WebhookPicker(Select):
    @property
    def view(self) -> WebhookPages:
        return self._view
    
    def __init__(self, view: WebhookPages) -> None:
        self._view = view
        
        super().__init__(
            placeholder="remove a webhook...",
            min_values=1,
            max_values=1,
            options=self.view.select_options
        )
    
    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer()
        view = Confirm(interaction.user)
        
        wh: WebhookData = self.view._webhooks[self.view.current_page].pop(idx := int(self.values[0]))
        n = wh["course_name"]
        embed = discord.Embed(
            title="confirm delete webhook",
            description=f"are you sure you want to delete the webhook for " \
                        f"**{n if len(n) <= 256 else n[:253] + '...'}** created in <#{wh['channel_id']}>?",
            colour=BotColours.red
        )
        msg = await interaction.followup.send(
            embed=embed, view=view, ephemeral=True, wait=True
        )
        view.original_message = msg
        
        expired = await view.wait()
        if expired:
            return await view.original_message.edit(view=view)
    
        await view.interaction.response.edit_message(view=view)
        if not view.choice:
            return await interaction.followup.send(
                "phew, dodged a bullet there", ephemeral=True
            )
        
        try:
            await Webhook.from_url(
                wh["url"],
                session=self.view.client.session,
                bot_token=self.view.client.token
            ).delete(reason=f"{interaction.user.name} ({interaction.user.id}) deleted webhook")
        except discord.NotFound:
            pass # meh their problem now
        
        await self.view.client.db.execute(DEL_QUERY,
            wh["user_id"],
            wh["course_id"],
            wh["channel_id"]
        )
        
        self.view._pages[self.view.current_page].remove_field(idx)
        if new_options := self.view.select_options:
            self.view.select_menu.options = new_options
        else:
            self.view.select_menu.disabled = True
        
        await interaction.edit_original_response(**self.view.edit_kwargs)


class WebhookPages(BasePages):
    WEBHOOKS_PER_PAGE = 12
    
    def __init__(
        self,
        interaction: Interaction,
        webhooks: List[WebhookData]
    ):
        self._pages = []
        self._current = 0
        self._parent = False
        self._interaction = interaction

        self._webhooks: List[WebhookData] = []
        
        self.webhooks_to_pages(webhooks=webhooks)
        
        super().__init__(timeout=self.TIMEOUT)
        
        self.select_menu = WebhookPicker(self)
        self.add_item(self.select_menu)
        for item in self.children:
            if isinstance(item, Button) and item is not self.button_current:
                item.callback = None
    
    def webhooks_to_pages(self, *, webhooks: List[WebhookData]):
        interaction = self._interaction

        while webhooks != []:
            page = discord.Embed()
            page.set_author(
                name=f"{interaction.user.name}#{interaction.user.discriminator}'s webhooks",
                icon_url=interaction.user.avatar.url
            )
            self._webhooks.append(bundle := webhooks[:self.WEBHOOKS_PER_PAGE])
            for webhook in bundle:
                n = webhook["course_name"]
                page.add_field(
                    name=n if len(n) <= 256 else n[:253] + "...",
                    value= \
                        f"— created in <#{webhook['channel_id']}>\n" \
                        f"— in guild `{self.client.get_guild(webhook['guild_id']).name}`"
                )
            self._pages.append(page)
            webhooks = webhooks[self.WEBHOOKS_PER_PAGE:]
    
    @property
    def select_options(self):
        return [
            discord.SelectOption(
                label=w["course_name"],
                value=idx,
            )
            for idx, w in enumerate(self._webhooks[self.current_page])
        ]
    
    async def interaction_check(self, interaction: Interaction, item: Item) -> bool:
        if (allowed := await super().interaction_check(interaction, item)):
            if isinstance(item, Button) and item is not self.button_current:
                if item is self.button_end:
                    self._current = self.page_count - 1
                elif item is self.button_next:
                    self._current += 1
                elif item is self.button_previous:
                    self._current -= 1
                else:
                    self._current = 0
                
                self.children[-1].options = self.select_options
                
                self.update_components()
                await interaction.response.edit_message(**self.edit_kwargs)
            
            if new_options := self.select_options:
                self.select_menu.disabled = False
                self.select_menu.options = new_options
            else:
                self.select_menu.disabled = True
        
        return allowed


class Webhooks(commands.Cog):
    def __init__(self, client: GClass) -> None:
        self.client = client
        
        fetch_posts.before_loop(client.wait_until_ready)
        self.running_task = fetch_posts.start(client)
    
    async def cog_unload(self) -> None:
        self.running_task.cancel()
    
    @command(name="webhooks")
    @is_logged_in()
    async def view_webhooks(self, interaction: Interaction):
        """
        view your configured webhooks
        """
        
        q = """SELECT * FROM webhooks
                WHERE user_id = $1
            """
        webhooks: List[WebhookData] = await self.client.db.fetch(q, interaction.user.id)
        if not webhooks:
            return await interaction.response.send_message(
                embed=discord.Embed(description="no webhooks to display"),
                ephemeral=True
            )
        
        await WebhookPages(interaction, webhooks).start()

    
async def setup(client: GClass):
    await client.add_cog(Webhooks(client=client))