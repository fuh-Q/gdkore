from __future__ import annotations

import asyncio
import csv
import io
import logging
import random
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from functools import partial
from PIL import Image, ImageFont, ImageDraw
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, Iterable, List, Literal, Tuple, TypeVar
from zipfile import ZipFile

import orjson

import discord
from discord import ui
from discord.app_commands import Choice, command, describe, autocomplete
from discord.ext import commands, tasks

from utils import CHOICES, BotEmojis, PrintColours, View, cap

if TYPE_CHECKING:
    from discord import Embed, File, InteractionMessage, Member, SelectOption, User

    from helper_bot import NotGDKID
    from utils import BusStopResponse, NGKContext, PostgresPool, RouteData, StopInfo, TripData

    from typing_extensions import Self

    T = TypeVar("T")
    Interaction = discord.Interaction[NotGDKID]
    TripField = List[TripData] | TripData | Dict[Literal["Trip"], List[TripData]] | Dict[Literal["Trip"], TripData]
    TripFetcher = Callable[[str], Coroutine[Any, Any, BusStopResponse]]
    EditFunc = Callable[..., Coroutine[Any, Any, InteractionMessage]]

    route_colour_cache: Dict[str, str]

log = logging.getLogger(f"NotGDKID:{__name__}")

RAIL = ["1"]
LRT_STATION_HINTS = (
    "O-TRAIN",
    "PARLIAMENT",
)

RELOAD_FAIL = "i couldn't reload that page, it's most likely that there were no trips left, therefore i've reset the menu to the landing screen"

STN_PATTERN = re.compile(r"(?: \d?[A-Z]$)| O-TRAIN(?:$| (?:WEST|EAST|NORTH|SOUTH) / (?:OUEST$|EST$|NORD$|SUD$))")
TITLECASE_PATTERN = re.compile(r"^\w| d'\w| \w|-\w")

GTFS_BUILD_INCLUDE = {
    "routes": ("route_short_name", "route_color", "route_text_color"),
    "stops": ("stop_code", "stop_name", "stop_lat", "stop_lon"),
}

no_routes_at_stop: Callable[[str], Embed] = lambda stop_code: discord.Embed(
    description=f"no trips that are anytime soon found for stop **#{stop_code}**", timestamp=datetime.now()
)

no_such_stop: Callable[[str], Embed] = lambda stop_code: discord.Embed(
    description=f"stop **#{stop_code}** does not exist", timestamp=datetime.now()
)

stop_search_query: Callable[[int], str] = lambda limit: (
    f"SELECT stop_code, stop_name FROM stops ORDER BY SIMILARITY(LOWER(stop_name), LOWER($1)) DESC LIMIT {limit}"
)


def _slice(obj: List[T], /, *, size: int = 25) -> Tuple[List[T]]:
    return tuple(obj[i : i + size] for i in range(0, len(obj), size))


def _get_trips_and_routes(o: List[RouteData] | RouteData) -> Tuple[List[TripData], List[RouteData]]:
    # for some reason, if there is only one route, OC Transpo will return just that single route object
    # rather than putting it in an array first to maintain type consistency
    # who the literal fuck designed this API lmao

    trips = []
    as_list = o if isinstance(o, list) else [o]
    for item in as_list:
        for trip in _parse_trips(item["Trips"]):
            trip["RouteNo"] = item["RouteNo"]
            trips.append(trip)

    return trips, as_list


def _parse_trips(o: TripField) -> List[TripData]:
    # for some reason, OC Transpo will sometimes return the "Trips" value as ANOTHER object
    # containing a single key, "Trip", which has the actual list we want
    # why.

    if isinstance(o, list):
        return o
    if "Trip" not in o:
        return [o]  # type: ignore

    return _parse_trips(o["Trip"])


def _sort_destinations(trips: List[TripData], /) -> List[str]:
    return sorted(
        {t["TripDestination"] for t in trips},
        key=lambda x: x[0],
    )


def _sort_routes(routes: List[RouteData], /) -> List[Tuple[str, str, List[TripData]]]:
    return sorted(
        ((f"[{i['RouteNo']}] {i['RouteHeading']}", i["RouteNo"], _parse_trips(i["Trips"])) for i in routes),
        key=lambda x: int(x[1]) if x[1].isnumeric() else 0,
    )


FONT = ImageFont.truetype("assets/opensans.ttf", 72)


def _generate_route_icon(route: str, /) -> Coroutine[Any, Any, File]:
    def runner():
        bg_colour, text_colour = route_colour_cache[route]

        buffer = io.BytesIO()
        img = Image.open(f"assets/{bg_colour}.png")
        draw = ImageDraw.Draw(img)

        textsize = FONT.getbbox(route)
        x, y = (img.width - textsize[2]) // 2, 4
        draw.text((x, y), route, fill="#" + text_colour, font=FONT)

        img.save(buffer, "png")
        buffer.seek(0)

        return discord.File(buffer, "penis.png", description="eat my balls")

    return asyncio.to_thread(runner)


async def _view_edit_kwargs(view: BusDisplay, *, as_send: bool = False) -> Dict[str, Any]:
    if view.sorting is Sorting.ROUTE:
        attachments = [await _generate_route_icon(view.current_key.split(":")[-1])]
    else:
        attachments = [discord.File("assets/penis.png")]

    file_key = "files" if as_send else "attachments"

    return {
        file_key: attachments,
        "embed": view.pages[view.current_key],
        "view": view,
    }


class BadResponse(Exception):
    def __init__(self, *args: Any, raw: Any = "") -> None:
        self.raw = raw
        super().__init__(*args)


class OCTranspoError(Exception):
    def __init__(self, error_embed: Embed, /) -> None:
        self.display = error_embed
        super().__init__()


class Sorting(Enum):
    ROUTE = 1
    DEST = 2


class BusDisplay(View, auto_defer=False):
    if TYPE_CHECKING:
        _data: BusStopResponse
        _stop_info: StopInfo
        _db: PostgresPool
        _destinations: Tuple[List[str]]
        _routes: Tuple[List[Tuple[str, str]]]
        _route_icons: Dict[str, File]
        _num_destinations: int
        _num_routes: int
        _owner: User | Member
        _trip_fetcher: TripFetcher

        current_key: str

    TIMEOUT = 120
    _pages: Dict[str, Embed] = {}
    _group: int = 0
    sorting: Sorting = Sorting.ROUTE

    @classmethod
    async def async_init(
        cls,
        *,
        data: BusStopResponse,
        db: PostgresPool,
        owner: User | Member,
        trip_fetcher: TripFetcher,
    ) -> Self:
        assert data["Routes"]["Route"] is not None
        trips, routes_raw = _get_trips_and_routes(data["Routes"]["Route"])

        destinations = _sort_destinations(trips)
        routes = _sort_routes(routes_raw)

        self = cls(timeout=cls.TIMEOUT)

        query = "SELECT * FROM stops WHERE stop_code = $1"
        self._stop_info: StopInfo = await db.fetchrow(query, data["StopNo"])  # type: ignore

        self._owner = owner
        self._data = data
        self._db = db
        self._destinations = _slice(destinations)
        self._routes = _slice([r[:2] for r in routes])
        self._num_destinations = len(destinations)
        self._num_routes = len(routes)
        self._trip_fetcher = trip_fetcher

        fullroute, route_no, _ = routes[0]
        self.current_key = f"r:{fullroute}:{route_no}"

        self._build_route_pages(routes)
        self._build_destination_pages(destinations)
        self.update_components()

        self.children[0].custom_id = self._make_custom_id()

        return self

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.client.is_blacklisted(interaction.user):
            await interaction.response.send_message("you're blacklisted \N{CLOWN FACE}", ephemeral=True)
            return False

        interaction.extras["recieved"] = True
        interaction.extras.setdefault("sender", interaction.response.send_message)
        interaction.extras.setdefault("editor", interaction.response.edit_message)

        if interaction.user.id != self._owner.id:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False

        return True

    @property
    def pages(self) -> Dict[str, Embed]:
        return self._pages

    @property
    def _collection(self) -> Tuple[List[str]] | Tuple[List[Tuple[str, str]]]:
        return self._routes if self.sorting is Sorting.ROUTE else self._destinations

    def _make_custom_id(self) -> str:
        return f"★;{self._stop_info['stop_code']};{self.current_key};{round(time.time())}"

    def _add_trip_fields_to_embed(self, embed: Embed, /, *, trips: List[TripData]) -> None:
        for i in range(3):
            name = f"Trip {i+1}"
            if i >= len(trips):
                embed.add_field(name=name, value="No data")
                continue

            trip = trips[i]
            cums_at = round((datetime.now() + timedelta(minutes=int(trip["AdjustedScheduleTime"]))).timestamp())

            arrives = f"**<t:{cums_at}:R>**"
            gps = f"GPS-adjusted? {BotEmojis.NO}"
            last_adjusted = "Last updated - N/A"

            assert embed.footer.text is not None
            if "destination" in embed.footer.text:
                mid = f"__Via Route__\n**`{trip['RouteNo']} {trip['TripDestination']}`**"
            else:
                mid = f"__Destination__\n**`{trip['TripDestination']}`**"

            if trips[i]["AdjustmentAge"] != "-1":
                gps = f"GPS-adjusted? {BotEmojis.YES}"
                last_adjusted = f"Updated {round(60*float(trip['AdjustmentAge']))}s ago"

            last_trip = f"Last trip? - {BotEmojis.YES if trip['LastTripOfSchedule'] else BotEmojis.NO}"
            embed.add_field(name=name, value=f"{arrives}\n\n{mid}\n\n{last_adjusted}\n{gps}\n{last_trip}\n\u200b")

    def _get_base_embed(self, item: str, value: str, /, *, route_no: str | None = None) -> Embed:
        e = discord.Embed(
            title=f"Next 3 trips for {item} {value}",
            timestamp=datetime.now(),
        )
        e.set_author(name=f"Bus Arrivals - {self._stop_info['stop_name']} [#{self._stop_info['stop_code']}]")
        e.set_footer(text=f"Sorting by {item}", icon_url=getattr(self._owner.avatar, "url", None))
        e.set_thumbnail(url="attachment://penis.png")

        if item == "route" and route_no is not None:
            today = datetime.now().strftime("%Y%m%d")
            e.url = f"https://octranspo.com/plan-your-trip/schedules-maps?sched-lang=en&date={today}&rte={route_no}"
        else:
            e.url = "https://cdn.discordapp.com/attachments/860182093811417158/1124050953692250224/image.png"

        return e

    def _build_route_pages(self, routes: List[Tuple[str, str, List[TripData]]], /) -> None:
        BASE = "r"

        for fullroute, route_no, trips in routes:
            key = f"{BASE}:{fullroute}:{route_no}"

            e = self._get_base_embed("route", fullroute, route_no=route_no)
            self._add_trip_fields_to_embed(e, trips=trips)
            self._pages[key] = e

    def _build_destination_pages(self, destinations: List[str], /) -> None:
        assert self._data["Routes"]["Route"] is not None
        BASE = "d"

        for dest in destinations:
            key = f"{BASE}:{dest}"

            e = self._get_base_embed("destination", dest)
            trips = sorted(
                (t for t in _get_trips_and_routes(self._data["Routes"]["Route"])[0] if t["TripDestination"] == dest),
                key=lambda x: int(x["AdjustedScheduleTime"]),
            )[:3]

            self._add_trip_fields_to_embed(e, trips=trips)
            self._pages[key] = e

    def _count_shown(self) -> str:
        start = 25 * self._group + 1
        total = self._num_routes if self.sorting is Sorting.ROUTE else self._num_destinations
        stop = min(total, start + len(self._collection[self._group]))

        return f"{start}-{stop} of {total}"

    @property
    def _bus_route_opts(self) -> List[SelectOption]:
        return [
            discord.SelectOption(label=f, value=f"r:{f}:{n}", description="Bus route" if n not in RAIL else "LRT line")
            for (f, n) in self._routes[self._group]  # (full route + destination, just the route number)
            if f"r:{f}:{n}" != self.current_key
        ]

    @property
    def _destination_opts(self) -> List[SelectOption]:
        return [
            discord.SelectOption(label=dest, value=f"d:{dest}", description="Destination")
            for dest in self._destinations[self._group]
            if f"d:{dest}" != self.current_key
        ]

    def _prepare_select(self) -> None:
        if self.sorting is Sorting.ROUTE:
            item = "Bus routes"
            opts = self._bus_route_opts
        else:
            item = "Destinations"
            opts = self._destination_opts

        self.mode_entity_select.placeholder = f"{item} [{self._count_shown()}]"
        self.mode_entity_select.disabled = not bool(opts)

        self.mode_entity_select.options = opts or [discord.SelectOption(label="suck my balls")]

    def update_components(self) -> None:
        self.children[0].custom_id = self._make_custom_id()
        self.previous_25.disabled = self._group == 0
        self.next_25.disabled = self._group == len(self._collection) - 1

        self.shown_counter.label = self._count_shown()
        self._prepare_select()

    # <-- actual components now lmfao -->

    @ui.button(label="❮", row=0, disabled=True, custom_id="prev25")
    async def previous_25(self, interaction: Interaction, item: ui.Button):
        if self._group > 0:
            self._group -= 1

        self.update_components()
        await interaction.extras["editor"](view=self)

    @ui.button(row=0, disabled=True, custom_id="counter")
    async def shown_counter(self, interaction: Interaction, item: ui.Button):
        await interaction.response.defer()

    @ui.button(label="❯", row=0, disabled=True, custom_id="next25")
    async def next_25(self, interaction: Interaction, item: ui.Button):
        if self._group < len(self._collection) - 1:
            self._group += 1

        self.update_components()
        await interaction.extras["editor"](view=self)

    @ui.button(emoji=BotEmojis.REFRESH, row=0, custom_id="refresh")
    async def refresh(self, interaction: Interaction, item: ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()

        try:
            new_data = await self._trip_fetcher(self._stop_info["stop_code"])
        except OCTranspoError as e:
            return await interaction.followup.send(embed=e.display, ephemeral=True)
        except BadResponse as e:
            return await interaction.followup.send(f"{str(e)}\n```json\n{e.raw!r}```", ephemeral=True)

        assert new_data["Routes"]["Route"] is not None
        trips, routes_raw = _get_trips_and_routes(new_data["Routes"]["Route"])

        destinations = _sort_destinations(trips)
        routes = _sort_routes(routes_raw)

        self._data = new_data
        self._destinations = _slice(destinations)
        self._routes = _slice([r[:2] for r in routes])
        self._num_destinations = len(destinations)
        self._num_routes = len(routes)

        self._pages = {}
        self._build_route_pages(routes)
        self._build_destination_pages(destinations)

        page = self._pages.get(self.current_key, None)
        if not page:
            fullroute, route_no, _ = routes[0]
            self.current_key = f"r:{fullroute}:{route_no}"
            self.sorting = Sorting.ROUTE

            await interaction.followup.send(RELOAD_FAIL, ephemeral=True)

        self.update_components()
        kwargs = await _view_edit_kwargs(self)
        await interaction.edit_original_response(**kwargs)

    @ui.select(row=1, custom_id="selector")
    async def mode_entity_select(self, interaction: Interaction, item: ui.Select):
        key = item.values[0]
        self.current_key = key

        self.update_components()
        kwargs = await _view_edit_kwargs(self)
        await interaction.extras["editor"](**kwargs)

    @ui.button(label="Sort by destination", row=2, custom_id="swap_sorting")
    async def swap_sorting(self, interaction: Interaction, item: ui.Button):
        if self.sorting is Sorting.ROUTE:
            self.sorting = Sorting.DEST
            self.current_key = f"d:{self._destinations[0][0]}"

            new_label = "Sort by route"
        else:
            fullroute, route_no = self._routes[0][0]
            self.sorting = Sorting.ROUTE
            self.current_key = f"r:{fullroute}:{route_no}"

            new_label = "Sort by destination"

        self._group = 0
        item.label = new_label

        self.update_components()
        kwargs = await _view_edit_kwargs(self)
        await interaction.extras["editor"](**kwargs)

    @ui.button(label="New lookup", row=2, style=discord.ButtonStyle.primary, custom_id="new_lookup")
    async def new_lookup(self, interaction: Interaction, item: ui.Button):
        self.update_components()
        if interaction.response.is_done():
            # responded in on_interaction
            return

        await interaction.response.send_modal(
            NewLookupModal(
                og_view=self,
                db=self._db,
                trip_fetcher=self._trip_fetcher,
            )
        )


class ResultSelector(View):
    def __init__(
        self,
        results: List[StopInfo],
        /,
        *,
        db: PostgresPool,
        trip_fetcher: TripFetcher,
        message_editor: EditFunc,
        owner: User | Member,
        og_view: BusDisplay | None = None,
    ) -> None:
        self._results = results
        self._db = db
        self._message_editor = message_editor
        self._trip_fetcher = trip_fetcher
        self._owner = owner
        self._og_view = og_view

        super().__init__(timeout=self.TIMEOUT)
        self._prepare_select()

        if not og_view:
            self.go_back.disabled = True

    async def on_timeout(self) -> None:
        if not self._og_view:
            self.disable_all()
            coro = self._message_editor(view=self)
        else:
            kwargs = await _view_edit_kwargs(self._og_view)
            coro = self._message_editor(**kwargs)

        try:
            await coro
        except discord.HTTPException:
            pass  # we tried

    async def interaction_check(self, interaction: Interaction, item: ui.Item) -> bool:
        if interaction.user.id != self._owner.id:
            await interaction.response.send_message(content=random.choice(CHOICES), ephemeral=True)
            return False
        return True

    def _prepare_select(self) -> None:
        transitway = []
        stops = []
        for r in self._results:
            if r["stop_name"].endswith(" Stn."):
                label = f"★  [{r['stop_code']}] {r['stop_name']}"
                description = "Transitway station"
                store = transitway
            else:
                label = f"[{r['stop_code']}] {r['stop_name']}"
                description = "Bus stop"
                store = stops

            store.append(discord.SelectOption(label=label, description=description, value=r["stop_code"]))

        self.selector.options = transitway + stops

    @ui.select(row=0, placeholder="Choose an option...")
    async def selector(self, interaction: Interaction, item: ui.Select):
        self.disable_all()
        item.placeholder = "just a sec..."
        await interaction.response.edit_message(view=self)
        search = item.values[0]

        try:
            data = await self._trip_fetcher(search)
        except OCTranspoError as e:
            return await interaction.followup.send(embed=e.display, ephemeral=True)
        except BadResponse as e:
            return await interaction.followup.send(f"{str(e)}\n```json\n{e.raw!r}```", ephemeral=True)

        assert data["Routes"]["Route"] is not None
        view = await BusDisplay.async_init(
            data=data,
            db=self._db,
            owner=interaction.user,
            trip_fetcher=self._trip_fetcher,
        )

        self.stop()
        if self._og_view:
            self._og_view.stop()

        kwargs = await _view_edit_kwargs(view)
        await interaction.edit_original_response(**kwargs)

    @ui.button(row=1, label="Go back")
    async def go_back(self, interaction: Interaction, item: ui.Button):
        assert self._og_view is not None

        self.stop()
        kwargs = await _view_edit_kwargs(self._og_view)
        await interaction.response.edit_message(**kwargs)

    @ui.button(label="New lookup", row=1, style=discord.ButtonStyle.primary, custom_id="new_lookup")
    async def new_lookup(self, interaction: Interaction, item: ui.Button):
        self.stop()
        await interaction.response.send_modal(
            NewLookupModal(
                og_view=self._og_view,
                db=self._db,
                trip_fetcher=self._trip_fetcher,
            )
        )


class NewLookupModal(ui.Modal, title="Bus Stop Lookup"):
    search = ui.TextInput(label="Search")

    def __init__(self, *, og_view: BusDisplay | None = None, db: PostgresPool, trip_fetcher: TripFetcher) -> None:
        self._og_view = og_view
        self._db = db
        self._trip_fetcher = trip_fetcher
        super().__init__()

    async def on_submit(self, interaction: Interaction):
        search = self.search.value
        if search.isnumeric() and len(search) == 4:
            await interaction.response.defer()

            try:
                data = await self._trip_fetcher(search)
            except OCTranspoError as e:
                return await interaction.followup.send(embed=e.display, ephemeral=True)
            except BadResponse as e:
                return await interaction.followup.send(f"{str(e)}\n```json\n{e.raw!r}```", ephemeral=True)

            assert data["Routes"]["Route"] is not None
            view = await BusDisplay.async_init(
                data=data,
                db=self._db,
                owner=interaction.user,
                trip_fetcher=self._trip_fetcher,
            )

            if self._og_view:
                self._og_view.stop()

            kwargs = await _view_edit_kwargs(view)
            return await interaction.edit_original_response(**kwargs)

        top_results: List[StopInfo] = await self._db.fetch(stop_search_query(10), search)
        if not top_results:
            return await interaction.response.send_message("nothing found...?", ephemeral=True)

        embed = discord.Embed(
            title=f"Results for Search '{cap(search):100}'",
            description="\n".join(f"— [`{r['stop_code']}`] {r['stop_name']}" for r in top_results),
            timestamp=datetime.now(),
        ).set_footer(icon_url=getattr(interaction.user.avatar, "url", None))

        view = ResultSelector(
            top_results,
            og_view=self._og_view,
            db=self._db,
            trip_fetcher=self._trip_fetcher,
            message_editor=interaction.edit_original_response,
            owner=interaction.user,
        )
        await interaction.response.edit_message(embed=embed, attachments=[], view=view)


class Transit(commands.Cog):
    def __init__(self, client: NotGDKID):
        self.client = client
        self._debug = False

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        if (
            not interaction.message
            or "recieved" in interaction.extras
            or interaction.type is not discord.InteractionType.component
            or not interaction.message.components
            or not interaction.message.interaction
            or not interaction.data
        ):
            return

        if self.client.is_blacklisted(interaction.user):
            return await interaction.response.send_message("you're blacklisted \N{CLOWN FACE}", ephemeral=True)

        items = interaction.message.components
        first = items[0].children[0] if isinstance(items[0], discord.ActionRow) else items[0]
        if not first.custom_id or not first.custom_id.startswith("★"):
            return

        stop_code, current_key, last_active_str = first.custom_id.split(";")[-3:]

        view_expired = int(last_active_str) + BusDisplay.TIMEOUT < time.time()
        bot_restarted = int(last_active_str) < self.client.uptime.timestamp() < int(last_active_str) + BusDisplay.TIMEOUT
        if not view_expired and not bot_restarted:
            # the view hasn't yet expired; handle interaction check in there
            return

        if interaction.user.id != interaction.message.interaction.user.id:
            return await interaction.response.send_message(random.choice(CHOICES), ephemeral=True)

        custom_id = interaction.data["custom_id"]  # type: ignore
        mapping = {"counter": 1, "next25": 2, "refresh": 3, "selector": 4, "swap_sorting": 5, "new_lookup": 6}

        if custom_id.startswith("★"):
            child_idx = 0
        else:
            child_idx = mapping[custom_id]

        interaction.extras["sender"] = interaction.followup.send
        interaction.extras["editor"] = interaction.edit_original_response
        if child_idx == 6:
            # we can only send modals in responses, so we've gotta do it here
            return await interaction.response.send_modal(
                NewLookupModal(
                    db=self.client.db,
                    trip_fetcher=self.fetch_trips,
                )
            )
        else:
            await interaction.response.defer()

        try:
            new_data = await self.fetch_trips(stop_code)
        except OCTranspoError as e:
            return await interaction.followup.send(embed=e.display, ephemeral=True)
        except BadResponse as e:
            return await interaction.followup.send(f"{str(e)}\n```json\n{e.raw!r}```", ephemeral=True)

        assert new_data["Routes"]["Route"] is not None
        view = await BusDisplay.async_init(
            data=new_data,
            db=self.client.db,
            owner=interaction.user,
            trip_fetcher=self.fetch_trips,
        )

        page = view.pages.get(current_key, None)
        if page is not None:
            view.current_key = current_key
            if current_key.startswith("d:"):
                view.sorting = Sorting.DEST
                view.swap_sorting.label = "Sort by route"
            else:
                view.sorting = Sorting.ROUTE
                view.swap_sorting.label = "Sort by destination"

        if child_idx == 3:
            # this entire event handler is inherently a refresh, we don't need to do it twice
            view.update_components()
            kwargs = await _view_edit_kwargs(view)
            await interaction.edit_original_response(**kwargs)

            if not page:
                await interaction.followup.send(RELOAD_FAIL, ephemeral=True)

            return

        item = view.children[child_idx]
        await view._scheduled_task(item, interaction)

        if child_idx == 6:
            # the new lookup button only sends the modal and calls it done
            # we need to actually edit the new view onto the message still
            # to prevent excessive calls to the API

            await interaction.edit_original_response(view=view)

    @classmethod
    def title(cls, s: str):
        """
        Problem with `str.title()` is that it misinterprets apostrophes as string boundaries, so we gotta fix that
        """

        return (
            TITLECASE_PATTERN.sub(lambda m: m.group().upper(), s.lower())
            .replace("Uottawa", "uOttawa")
            .replace("H.s", "H.S")
            .replace("toh", "T.O.H.")
            .replace("Toh", "T.O.H.")
        )

    async def cog_load(self):
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        until_midnight = midnight - now

        self.gtfs_task = tasks.loop(hours=24)(self._build_gtfs_tables)
        self.gtfs_task.before_loop(partial(asyncio.sleep, until_midnight.total_seconds()))
        self.gtfs_task.start(include=GTFS_BUILD_INCLUDE)

    async def cog_unload(self):
        self.gtfs_task.cancel()

    async def fetch_trips(self, stop_code: str, /) -> BusStopResponse:
        url = "https://api.octranspo1.com/v2.0/GetNextTripsForStopAllRoutes"
        params = {
            "appID": self.client.transit_id,
            "apiKey": self.client.transit_token,
            "stopNo": stop_code,
            "format": "json",
        }

        async with self.client.session.get(url, params=params) as res:
            raw = await res.text()

        if self._debug:
            log.info(raw)

        try:
            data = orjson.loads(raw)["GetRouteSummaryForStopResult"]
        except orjson.JSONDecodeError:
            # when the API errors out, it spews XML
            # heck, even when you specify json as a format in your request
            # the response content-type is plain text/html nonetheless
            # great job with that OC

            maybe_json = raw.split("\n")[-1].split(">")[-1]
            try:
                data = orjson.loads(maybe_json)["GetRouteSummaryForStopResult"]
            except (orjson.JSONDecodeError, KeyError):
                raise BadResponse(
                    "bad response from OC Transpo, failed serializing to JSON, so here's the raw request output",
                    raw=raw,
                )

        if "StopDescription" not in data or "Routes" not in data:
            raise BadResponse("invalid payload from OC Transpo", raw=data)

        if not data["StopDescription"] or not data["Routes"]["Route"]:
            embed = no_such_stop(stop_code) if not data["StopDescription"] else no_routes_at_stop(stop_code)
            raise OCTranspoError(embed)

        return data

    async def _do_bulk_insert(self, table: str, buffer: io.BytesIO, *columns: str) -> None:
        sql_columns = ", ".join(f"{c} TEXT" for c in columns)

        # we do like a shit ton of string interpolation in our queries here...
        # but it's okay in this specific case since the end user never has access to the parameters being injected
        async with self.client.db.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute(f"DELETE FROM {table}; CREATE TEMP TABLE tmp ({sql_columns}) ON COMMIT DROP")
                await conn.copy_to_table("tmp", source=buffer, columns=columns, header=False, format="csv")

                query = f"INSERT INTO {table} SELECT * FROM tmp ON CONFLICT DO NOTHING"
                await conn.execute(query)
            except Exception as e:
                await tr.rollback()
                log.error("failed rebuilding gtfs table '%s': %s", table, e)

                raise
            else:
                await tr.commit()

    def _parse_csv_line(self, row: List[str], /, columns: Tuple[str], colindexes: Tuple[int]) -> List[str]:
        filtered = [row[i] for i in colindexes]

        # special casing for the stops table, for transitway stations
        # essentially there are separate records of all the individual bus stands at a station that all share one stop code
        # that are all being amalgamated into one single entity

        if "stop_name" in columns:
            i = columns.index("stop_name")
            if "/" not in filtered[i] or any(n in filtered[i] for n in LRT_STATION_HINTS):
                filtered[i] = STN_PATTERN.sub(" stn.", filtered[i])

            filtered[i] = self.title(filtered[i])

        return filtered

    def _parse_csv_to_bytesio(self, zipfile: ZipFile, table: str, *columns: str) -> io.BytesIO:
        raw = zipfile.read(table + ".txt")
        reader = csv.reader(io.StringIO(raw.decode()))
        buffer = io.BytesIO()

        # first line contains column names
        colnames = next(reader)
        colindexes = tuple(i for i, column in enumerate(colnames) if column in columns)

        if len(colindexes) < len(columns):
            diff = len(colindexes) - len(columns)
            log.warn("%d column(s) were not found whilst building table '%s'", diff, table)

        new_content = ""

        for row in reader:
            filtered = self._parse_csv_line(row, columns, colindexes)
            if all(i for i in filtered):
                new_content += f"{','.join(filtered)}\n"

        buffer.write(new_content.strip().encode())
        buffer.seek(0)
        return buffer

    def _handle_zipfile(self, the_zip: io.BytesIO, *tables: str, **columns: Iterable[str]) -> Dict[str, io.BytesIO]:
        buffers = {}
        with ZipFile(the_zip, "r") as zipfile:
            for table in tables:
                if table + ".txt" in zipfile.namelist():
                    buffers[table] = self._parse_csv_to_bytesio(zipfile, table, *columns[table])
                else:
                    log.warn("%s table not found in gtfs data", table)

        return buffers

    async def _build_gtfs_tables(self, *, include: Dict[str, Iterable[str]]) -> bool:
        url = "https://www.octranspo.com/files/google_transit.zip"
        successful = True

        log.info("attempting to build gtfs tables...")

        async with self.client.session.get(url) as resp:
            if resp.status == 200:
                buffer = io.BytesIO(await resp.read())
            else:
                colour = PrintColours.RED if resp.status >= 400 else PrintColours.GREEN
                log.error("could not build gtfs tables (response code: %s%d%s)", colour, resp.status, PrintColours.WHITE)

                return False

        tables = tuple(include)
        buffers = await asyncio.to_thread(self._handle_zipfile, buffer, *tables, **include)
        for filename, buffer in buffers.items():
            try:
                await self._do_bulk_insert(filename, buffer, *include[filename])
            except Exception:
                successful = False

        log.info("gtfs build %s", "complete" if successful else "errored")
        return successful

    async def stop_or_station_autocomplete(self, interaction: Interaction, current: str) -> List[Choice[str]]:
        if not current:
            return [Choice(name="Enter a stop name...", value="")]

        results: List[StopInfo] = await self.client.db.fetch(stop_search_query(25), current)
        return [
            Choice(
                name=f"{'★  ' if r['stop_name'].endswith(' Stn.') else ''}[{r['stop_code']}] {r['stop_name']}",
                value=r["stop_code"],
            )
            for r in results
        ]

    @command(name="busarrivals", description="oc transpo bus arrivals")
    @describe(stop_or_station="the station or bus stop to view arrivals for")
    @autocomplete(stop_or_station=stop_or_station_autocomplete)
    async def bus(self, interaction: Interaction, stop_or_station: str):
        if not stop_or_station:
            return await interaction.response.send_message("?", ephemeral=True)

        if not stop_or_station.isnumeric() or not len(stop_or_station) == 4:
            top_results: List[StopInfo] = await self.client.db.fetch(stop_search_query(10), stop_or_station)
            if not top_results:
                return await interaction.response.send_message("nothing found...?", ephemeral=True)

            embed = discord.Embed(
                title=f"Results for Search '{cap(stop_or_station):100}'",
                description="\n".join(f"— [`{r['stop_code']}`] {r['stop_name']}" for r in top_results),
                timestamp=datetime.now(),
            ).set_footer(icon_url=getattr(interaction.user.avatar, "url", None))

            view = ResultSelector(
                top_results,
                db=self.client.db,
                trip_fetcher=self.fetch_trips,
                message_editor=interaction.edit_original_response,
                owner=interaction.user,
            )
            return await interaction.response.send_message(embed=embed, view=view)

        await interaction.response.defer()

        try:
            data = await self.fetch_trips(stop_or_station)
        except OCTranspoError as e:
            return await interaction.followup.send(embed=e.display, ephemeral=True)
        except BadResponse as e:
            return await interaction.followup.send(f"{str(e)}\n```json\n{e.raw!r}```", ephemeral=True)

        assert data["Routes"]["Route"] is not None
        view = await BusDisplay.async_init(
            data=data,
            db=self.client.db,
            owner=interaction.user,
            trip_fetcher=self.fetch_trips,
        )

        kwargs = await _view_edit_kwargs(view, as_send=True)
        await interaction.followup.send(**kwargs)

    @command(name="routemap", description="view a bus route's map")
    @describe(route="the route number")
    async def routemap(self, interaction: Interaction, route: str):
        route = route.upper()

        if route not in route_colour_cache:
            msg = f"route **{route}** does not exist"
            return await interaction.response.send_message(msg, ephemeral=True)

        today = datetime.now().strftime("%Y%m%d")
        title_url = f"https://octranspo.com/plan-your-trip/schedules-maps?sched-lang=en&date={today}&rte={route}"
        url = f"https://octranspo.com/images/files/routes/{route.zfill(3)}map.gif"

        embed = discord.Embed(title=f"Route map for route {route}", url=title_url).set_image(url=url)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="gtfs")
    @commands.is_owner()
    async def gtfs(self, ctx: NGKContext):
        successful = await self._build_gtfs_tables(include=GTFS_BUILD_INCLUDE)
        if not successful:
            return await ctx.reply("build errored, check logs")

        await ctx.try_react(emoji=BotEmojis.YES)

    @commands.command(name="busdebug", aliases=["bdg"])
    @commands.is_owner()
    async def busdebug(self, ctx: NGKContext):
        self._debug = not self._debug
        await ctx.reply(f"api debugging {'enabled' if self._debug else 'disabled'}")


async def setup(client: NotGDKID):
    global route_colour_cache

    query = "SELECT * FROM routes"
    route_colour_cache = {r["route_short_name"]: r[1:] for r in await client.db.fetch(query)}

    await client.add_cog(Transit(client=client))
