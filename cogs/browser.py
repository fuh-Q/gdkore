from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from functools import partial
from itertools import chain
from typing import Any, Dict, Generic, List, Iterable, Tuple, TypeVar, TYPE_CHECKING

import discord
from discord.app_commands import checks, command
from discord.ext import commands
from discord.ui import (
    button,
    Button,
    Select,
)

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, HttpError

from utils import (
    BasePages,
    BotEmojis,
    BotColours,
    Confirm,
    GoogleChunker,
    View,
    format_google_time,
    is_logged_in,
)

if TYPE_CHECKING:
    from discord import Interaction
    from discord.ui import Item
    
    from bot import GClass
    from utils import (
        Attachment,
        Course,
        CourseWork,
        Resource
    )


KT = TypeVar("KT")
VT = TypeVar("VT", bound=Iterable)
HomeT = TypeVar("HomeT", bound=BasePages)

class ExpiringDict(dict, Generic[KT, VT]):
    def __init__(self, timeout: int, *, will_refresh: bool = True):
        self.timeout: int = timeout
        self._will_refresh: bool = will_refresh
    
    def get(self, k: KT, default: Any | None = None) -> VT | None:
        value = super().get(k, default)
        if value:
            return value[0]
    
    def _refresh_timeout(self, k: KT) -> None:
        if self._will_refresh:
            value = super().get(k, None)
            if value:
                value[1] = time.monotonic()
    
    def _clear_expired(self) -> None:
        now = time.monotonic()
        expired: Tuple[KT] = tuple(k for (k, (v, t)) in self.items() if now - t > self.timeout)
        for key in expired:
            del self[key]
    
    def __contains__(self, key: KT) -> bool:
        self._clear_expired()
        self._refresh_timeout(key)
        return super().__contains__(key)
    
    def __getitem__(self, key: KT) -> VT:
        self._clear_expired()
        self._refresh_timeout(key)
        value = super().__getitem__(key)
        return value[0]
    
    def __setitem__(self, k: KT, v: VT) -> None:
        self._clear_expired()
        super().__setitem__(k, [v, time.monotonic()])
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

ICONS: Dict[str, str] = {
    "announcement": "https://i.vgy.me/KUQqCn.png",
    "material": "https://i.vgy.me/ANpclU.png",
    "assignment": "https://i.vgy.me/0lnb2d.png",
    "multiple choice question": "https://i.vgy.me/bt97OS.png",
    "short answer question": "https://i.vgy.me/bt97OS.png",
    "posted": "https://i.vgy.me/q8ExVs.png",
}

def get_due_date(assignment: CourseWork) -> datetime | None:
    if not (due := assignment.get("dueDate", None)):
        return
    
    due_date = datetime(due["year"], due["month"], due["day"], tzinfo=timezone.utc)
    if time := assignment.get("dueTime", None):
        kwargs = {"hour": time.get("hours", 0)}
        if m := time.get("minutes", None):
            kwargs["minute"] = m
        due_date = due_date.replace(**kwargs)
    
    return due_date


class GoBack(View, Generic[HomeT]):
    __parameters__ = (0,)
    
    def __init__(self, homepage: HomeT):
        self._home = homepage
        
        super().__init__(timeout=self.TIMEOUT)
    
    async def on_timeout(self) -> None:
        self.disable_all(exclude_urls=True)

        try:
            await self._home._interaction.edit_original_response(view=self)
        except discord.HTTPException:
            pass # we tried
    
    async def on_error(self, interaction: Interaction, error: Exception, item: Item) -> None:
        if isinstance(error, RefreshError):
            return self._home.client.dispatch("app_command_error", interaction, error)
        
        raise error
    
    async def interaction_check(self, interaction: Interaction, item: Item) -> bool:
        self.stop()
        
        return True
    
    async def after_callback(self, interaction: Interaction, item: Item):
        self._home._refresh_timeout() # refresh CoursePages object
    
    @button(label="go back", style=discord.ButtonStyle.success)
    async def return_home(self, interaction: Interaction, button: Button):
        self._home._parent = False
        await self._home.start(edit_existing=True, interaction=interaction)


class CoursePages(BasePages):
    COURSES_PER_PAGE = 12
    credentials: Credentials
    
    cache: Dict[str, Tuple[List[CourseWork], Course]]
    
    def __init__(
        self,
        interaction: Interaction,
        courses: List[Course],
        service: Resource,
    ):
        self._resource = service
        
        self._pages = []
        self._current = 0
        self._parent = False
        self._interaction = interaction

        self._courses = []
        
        self.cache = {}
        
        self.courses_to_pages(courses=courses)
        
        super().__init__(timeout=self.TIMEOUT)
        
        self.select_menu = ClassPicker(self)
        self.add_item(self.select_menu)
        for item in self.children:
            if isinstance(item, Button) and item is not self.button_current:
                item.callback = None # type: ignore
    
    def courses_to_pages(self, *, courses: List[Course]) -> None:
        interaction = self._interaction

        while courses != []:
            page = discord.Embed()
            page.set_author(
                name=f"{interaction.user.name}#{interaction.user.discriminator}'s courses",
                icon_url=interaction.user.display_avatar.url
            )
            self._courses.append(bundle := courses[:self.COURSES_PER_PAGE])
            for course in bundle:
                page.add_field(
                    name=course["name"],
                    value=f"[*`course id` —* `{course['id']}`]({course['alternateLink']})"
                )
            self._pages.append(page)
            courses = courses[self.COURSES_PER_PAGE:]
        
    @property
    def select_options(self):
        return [
            discord.SelectOption(
                label=c["name"],
                value=c["id"],
            )
            for c in self._courses[self.current_page]
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
                
                self.select_menu.options = self.select_options
                
                self.update_components()
                await interaction.response.edit_message(**self.edit_kwargs)
        
        return allowed

class ClassPicker(Select[CoursePages]):
    _view: CoursePages
    
    @property
    def view(self) -> CoursePages:
        return self._view
    
    def __init__(self, view: CoursePages) -> None:
        self._view = view
        
        super().__init__(
            placeholder="view class assignments...",
            min_values=1,
            max_values=1,
            options=self.view.select_options
        )
    
    async def callback(self, interaction: Interaction) -> None:
        await interaction.response.defer()
        self.view._parent = True
        
        if from_cache := self.view.cache.get(self.values[0], None):
            assignments, course = from_cache
        else:
            assignments = None
            course = next(filter(
                lambda i: i["id"] == self.values[0], chain.from_iterable(self.view._courses)
            ))
        
        menu = ClassHome(
            self.view,
            interaction,
            course,
            self.view._resource,
            assignments
        )
        menu.original_message = self.view.original_message
        
        e = discord.Embed(
            title=course["name"],
            description=f"{course.get('descriptionHeading', '')}\n\n{course.get('description', '')}"
        )
        await interaction.edit_original_response(
            embed=e,
            view=menu
        )


class ClassHome(GoBack[CoursePages]):
    client: GClass
    
    def __init__(
        self,
        homepage: CoursePages,
        interaction: Interaction,
        course: Course,
        service: Resource,
        assignments_from_cache: List[CourseWork] | None = None
    ):
        self._home = homepage
        self._resource = service
        self._course = course
        self._interaction = interaction
        self._assignments = assignments_from_cache
        
        self.client = interaction.client # type: ignore
        
        super().__init__(homepage=homepage)
    
    def run_google(self, service: Resource, nextPageToken: str | None = None): # all of the google libs are sync
        if nextPageToken is not None:
            extras = {
                "pageToken": nextPageToken,
                "pageSize": 50
            }
        else:
            extras = {
                "pageSize": 10
            }
        
        return service.courses().courseWork().list(
            courseId=self._course["id"],
            orderBy="updateTime desc, dueDate desc",
            **extras
        ).execute()
    
    @button(label="setup webhook", style=discord.ButtonStyle.primary)
    async def setup_webhook(self, interaction: Interaction, button: Button):
        if not interaction.guild:
            return await interaction.response.edit_message(
                embed=discord.Embed(description="you can't set a webhook in dms"),
                view=GoBack(self._home)
            )
        
        edit = partial(interaction.response.edit_message, view=GoBack(self._home))
        edit_original = partial(interaction.edit_original_response, view=GoBack(self._home))
        
        assert interaction.channel and isinstance(interaction.user, discord.Member)
        if not interaction.channel.permissions_for(interaction.user).manage_channels:
            return await edit(embed=discord.Embed(
                description="you need the `manage channels` permission in order to perform this operation"
            ))
        
        q = """SELECT 1 FROM webhooks
                WHERE user_id = $1
                AND course_id = $2
                AND channel_id = $3
            """
        if await self.client.db.fetchval(q,
            self._interaction.user.id,
            int(self._course["id"]),
            interaction.channel_id
        ):
            return await edit(embed=discord.Embed(description="this webhook already exists"))
        
        view = Confirm(interaction.user)
        embed = discord.Embed(
            title="create a webhook",
            description=f"confirm you want to receive notifications from **{self._course['name']}** " \
                        f"in <#{interaction.channel.id}>?"
        ).set_footer(
            text="note that due to a limitation imposed by google, you can't " \
                  "create a webhook for a course owned by your own account." \
                  "\n\nwe're assuming you don't own this course, but if your webhook breaks, " \
                  "you'll know why."
        )
        await interaction.response.edit_message(
            embed=embed, view=view
        )
        view.original_message = await interaction.original_response()
        
        expired = await view.wait()
        if expired:
            return await interaction.edit_original_response(view=view)
        
        if not view.choice:
            return await view.interaction.response.edit_message(
                embed=discord.Embed(description="phew, dodged a bullet there"),
                view=GoBack(self._home)
            )
        else:
            await view.interaction.response.edit_message(
                embed=discord.Embed(description=f"{BotEmojis.LOADING} setting webhook..."),
                view=None
            )
        
        try:
            assert isinstance(interaction.channel, discord.TextChannel)
            wh = await interaction.channel.create_webhook(
                name=self._course["name"],
                avatar=self.client.avatar_bytes,
                reason=f"{interaction.user.name} ({interaction.user.id}) configured webhook"
            )
        except discord.Forbidden:
            e = discord.Embed(
                description="failed to create the webhook, make sure i have `manage webhook` permissions"
            )
            return await edit_original(embed=e)
        except Exception as err:
            e = discord.Embed(title="error creating webhook", description=f"```py\n{err}\n```")
            return await edit_original(embed=e)
        
        q = """INSERT INTO webhooks VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT ON CONSTRAINT webhooks_pkey
                DO NOTHING
            """
        await self.client.db.execute(q,
            self._interaction.user.id,
            int(self._course["id"]),
            self._interaction.guild_id,
            self._interaction.channel_id,
            self._course["name"],
            wh.url,
            *(datetime.now(tz=timezone.utc),) * 4
        )
        n = self._course["name"]
        n = n if len(n) <= 256 else n[:253] + "..."
        desc = f"successfully created a webhook for **{n}** " \
               f"in <#{interaction.channel.id}>!"
        
        await edit_original(embed=discord.Embed(description=desc))
    
    @button(label="view assignments", style=discord.ButtonStyle.primary)
    async def view_attachments(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        next_page: str | None = None
        
        if (assignments := self._assignments) is None:
            e = discord.Embed(
                description=f"{BotEmojis.LOADING} fetching data..."
            )
            await interaction.edit_original_response(embed=e, view=None)
            try:
                assignments = await asyncio.to_thread(self.run_google, service=self._resource)
            except HttpError:
                e = discord.Embed(
                    description= \
                        "you can't view assignments from a course owned by your own account." \
                        "\ngoogle made it this way, there's literally nothing i can do about it lol"
                )
                return await interaction.edit_original_response(
                    embed=e, view=GoBack(self._home)
                )
            
            next_page = assignments.get("nextPageToken", "")
            assignments = assignments.get("courseWork", None)
        
        if not assignments:
            if not self._home.cache.get(self._course["id"], None):
                self._home.cache[self._course["id"]] = [], self._course
            
            e = discord.Embed(description="no course work to display")
            return await interaction.edit_original_response(
                embed=e, view=GoBack(self._home)
            )
        
        content = None
        menu: ClassMenu = await ClassMenu().async_init(
            self._home,
            self._interaction,
            self._course,
            assignments,
            self._resource
        )
        if menu.pages[0].colour:
            content = ClassMenu.get_content(assignments[0])
        await menu.start(edit_existing=True, interaction=interaction, content=content)
        
        if not next_page:
            return # we don't need to worry about fetching the remaining data
        
        assignment_chunks: GoogleChunker[CourseWork] = GoogleChunker(
            self.client.loop, self.run_google, next_page, self._resource # type: ignore
        )
        async for assignments in assignment_chunks:
            menu._assignments += assignments
            
            for assignment in assignments:
                menu._pages.append(await menu.make_embed(assignment))

class ClassMenu(BasePages):
    async def async_init(
        self,
        homepage: CoursePages,
        interaction: Interaction,
        course: Course,
        assignments: List[CourseWork],
        service: Resource,
    ):
        self._home: CoursePages = homepage
        self._resource: Resource = service
        self._course: Course = course
        
        self._pages = []
        self._current = 0
        self._parent = False
        self._interaction = interaction
        
        for assignment in assignments:
            page = await self.make_embed(assignment)
            self._pages.append(page)
        
        self._assignments = assignments
        
        if not self._home.cache.get(course["id"], None):
            self._home.cache[course["id"]] = assignments, course
        
        if not assignments[0].get("materials", None):
            self.remove_item(self.view_attachments)
        
        self.remove_item(self.button_start)
        self.remove_item(self.button_end)
        
        self._children.insert(0, self._children.pop(self._children.index(
            self.return_home
        )))
        
        self.ass_link = Button(
            label="view in classroom",
            style=discord.ButtonStyle.link,
            url=assignments[0]["alternateLink"],
        )
        self.add_item(self.ass_link)
        
        return self
    
    async def make_embed(self, assignment: CourseWork) -> discord.Embed:
        def run_google(assignmentId): # all google libs are sync
            submissions = service.courses().courseWork().studentSubmissions().list(
                courseId=self._course["id"],
                courseWorkId=assignmentId,
                userId="me",
            ).execute()
            
            return submissions["studentSubmissions"][0]
        
        service = self._resource
        timestamp = format_google_time(assignment)
        
        assignment_response = assignment["workType"].lower().replace("_", " ")
        t = assignment.get("title", "")
        d = assignment.get("description", "")
        n = self._course["name"]
        page = discord.Embed(
            title=t if len(t) <= 256 else t[:253] + "...",
            description=d if len(d) <= 4096 else d[:4093] + "...",
            timestamp=timestamp,
            url=assignment["alternateLink"]
        ).set_footer(
            text="posted at",
            icon_url=ICONS["posted"]
        ).set_author(
            name=n if len(n) <= 256 else n[:253] + "...",
            icon_url=ICONS[assignment_response],
            url=assignment["alternateLink"]
        )
        
        name = value = ""
        if (due_date := get_due_date(assignment)):
            if (submission := assignment.get("studentSubmissions", None)) is None:
                submission = await asyncio.to_thread(run_google, assignment["id"])
            
            state = submission["state"]
            worktype = submission["courseWorkType"]
            if not_turned_in := state not in ("TURNED_IN", "RETURNED"):
                name = "assignment due"
                value = f"<t:{int(due_date.timestamp())}:R>"
            else:
                if worktype == "ASSIGNMENT":
                    name = "you handed in"
                    value = f"{len(submission['assignmentSubmission'].get('attachments', []))} attachments"
                elif worktype in ("MULTIPLE_CHOICE_QUESTION", "SHORT_ANSWER_QUESTION"):
                    if worktype == "MULTIPLE_CHOICE_QUESTION":
                        v = submission["multipleChoiceSubmission"]["answer"]
                    else:
                        v = submission["shortAnswerSubmission"]["answer"]
                    
                    name = "you answered"
                    value = v if len(v) <= 69 else v[:69] + "..."
            
            if not_turned_in:
                now_utc = datetime.utcnow()
                if now_utc.timestamp() >= due_date.timestamp():
                    page.colour = BotColours.red
                elif due_date.timestamp() - now_utc.timestamp() <= 172800: # 2 days away
                    page.colour = BotColours.yellow
            
            if not assignment.get("studentSubmissions", None):
                assignment["studentSubmissions"] = submission
        else:
            name = "assignment due"
            value = "no due date"
        
        page.add_field(name=name, value=value)
        
        if (points := assignment.get("maxPoints", None)):
            page.add_field(
                name="obtainable points",
                value=points
            )
        
        return page
    
    async def interaction_check(self, interaction: Interaction, item: Item) -> bool:
        if (
            (allowed := await super().interaction_check(interaction, item))
            and item in (self.button_previous, self.button_next)
        ):
            op = int.__add__ if item is self.button_next else int.__sub__
            index = op(self.current_page, 1)
            if self._assignments[index].get("materials", None) and self.view_attachments not in self.children:
                self.add_item(self.view_attachments)
            else:
                self.remove_item(self.view_attachments)
            
            self.ass_link.url = self._assignments[index]["alternateLink"]
        
        return allowed
    
    async def after_callback(self, interaction: Interaction, item: Item):
        self._home._refresh_timeout() # refresh CoursePages object
    
    def update_components(self):
        self.button_next.disabled = (self._current == self.page_count - 1)
        self.button_previous.disabled = (self._current == 0)
        
        self.button_current.label = f"{self.current_page + 1} / {self.page_count}"
    
    @staticmethod
    def get_content(assignment: CourseWork) -> str:
        if not (due := get_due_date(assignment)):
            return ""
        
        time_int = int(due.timestamp())
        
        now_utc = datetime.utcnow()
        if now_utc.timestamp() >= due.timestamp():
            return f"{BotEmojis.RED_WARNING}" + \
                  f" **assignment late or __due very soon.__ ㅤㅤ [<t:{time_int}:R>]** " + \
                   f"{BotEmojis.RED_WARNING}\n\u200b"
        elif due.timestamp() - now_utc.timestamp() <= 172800: # 2 days away:
            return "\N{WARNING SIGN}" \
                  f" assignment due soon. ㅤㅤ [<t:{time_int}:R>] " \
                   "\N{WARNING SIGN}\n\u200b"
        
        return ""
    
    @property
    def edit_kwargs(self):
        kwargs = {
            "content": None,
            "view": self
        }
        
        embed = self.pages[self.current_page]
        if embed.colour:
            content = self.get_content(self._assignments[self.current_page])
            
            self.original_message.content = content
            kwargs["content"] = content
        kwargs["embed"] = embed
        
        return kwargs
    
    @button(label="go back", style=discord.ButtonStyle.success, row=1)
    async def return_home(self, interaction: Interaction, button: Button):
        self._home._parent = False
        await self._home.start(edit_existing=True)
        self.stop()
    
    @button(label="view assignment materials", style=discord.ButtonStyle.primary, row=1)
    async def view_attachments(self, interaction: Interaction, button: Button):
        ass = self._assignments[self.current_page]
        self._parent = True
        
        view = AttachmentsView(
            homepage=self, attachments=ass["materials"], service=self._resource, content=self.original_message.content
        )
        view.original_message = self.original_message
        await interaction.response.edit_message(view=view)

class AttachmentsView(GoBack[ClassMenu]):
    def __init__(
        self,
        homepage: ClassMenu,
        attachments: List[Attachment],
        service: Resource,
        content: str | None = None
    ):
        self._home = homepage
        self._resource = service
        
        self._content = content
        
        super().__init__(homepage=homepage)
        
        self.weights.weights[0] = 5
        self.add_attachments(attachments, self)
    
    @staticmethod
    def add_attachments(attachments: List, view: View):
        for attachment in attachments:
            if (k := list(attachment.keys())[0]) == "form":
                a = attachment[k]
                url = a["formUrl"]
            elif k == "link":
                a = attachment[k]
                url = a["url"]
            elif k == "driveFile":
                a = attachment[k][k]
                url = a["alternateLink"]
            else:
                a = attachment[k]
                url = a["alternateLink"]
            
            emojis = {
                "driveFile": BotEmojis.DRIVE,
                "form": BotEmojis.FORMS,
                "link": BotEmojis.LINK,
                "youtubeVideo": BotEmojis.YOUTUBE,
            }

            t = a.get("title", "Untitled")
            view.add_item(Button(
                label=t if len(t) < 80 else t[:77] + "...",
                emoji=emojis[k],
                style=discord.ButtonStyle.link,
                url=url
            ))
    
    async def after_callback(self, interaction: Interaction, item: Item):
        self._home._home._refresh_timeout() # refresh CoursePages object
        self._home._refresh_timeout() # refresh ClassMenu object


class Browser(commands.Cog):
    def __init__(self, client: GClass):
        self.client = client
        
        self.course_cache: ExpiringDict[int, List[Course]] = ExpiringDict(300)
    
    @command(name="courses")
    @is_logged_in()
    @checks.cooldown(1, 15)
    async def list_courses(self, interaction: Interaction):
        """
        lists your courses. you can also pick on a course to view specific things
        """
        
        def run_google_service(credentials) -> Resource: # all of the google libs are sync
            creds = Credentials.from_authorized_user_info(
                credentials, scopes=self.client.SCOPES
            )
            return build("classroom", "v1", credentials=creds)
        
        def run_google_courses(nextPageToken = None) -> Dict: # all of the google libs are sync
            kwargs = {
                "pageSize": 50
            }
            if nextPageToken is not None:
                kwargs["pageToken"] = nextPageToken
            
            return service.courses().list(**kwargs).execute()
        
        await interaction.response.defer(ephemeral=True)
        data = interaction.extras["credentials"]
        
        next_page: str | None = None
        service = await asyncio.to_thread(run_google_service, data)
        
        if not (courses := self.course_cache.get(interaction.user.id, None)):
            courses = await asyncio.to_thread(run_google_courses)
            next_page = courses.get("nextPageToken", None)
            courses = courses.get("courses", [])
            
        self.course_cache[interaction.user.id] = courses
        
        if not courses:
            return await interaction.response.send_message(
                embed=discord.Embed(description="no courses to display"),
                ephemeral=True
            )
        
        menu = CoursePages(interaction, courses, service)
        await menu.start()
        
        if not next_page:
            return # we don't need to worry about fetching the remaining data
        
        course_chunks: GoogleChunker[Course] = GoogleChunker(self.client.loop, run_google_courses, next_page)
        async for courses in course_chunks:
            self.course_cache[interaction.user.id] += courses
            
            last_embed_slots_remaining = menu.COURSES_PER_PAGE - len(menu.pages[-1].fields)
            for _ in range(last_embed_slots_remaining):
                course = courses.pop(0)
                menu.pages[-1].add_field(
                    name=course["name"],
                    value=f"[*`course id` —* `{course['id']}`]({course['alternateLink']})"
                )
                menu._courses[-1].append(course)
            
            menu.courses_to_pages(courses=courses)


async def setup(client: GClass):
    await client.add_cog(Browser(client=client))
