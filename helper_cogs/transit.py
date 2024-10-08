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
from discord.utils import cached_property

from utils import CHOICES, AsyncInit, BotEmojis, PrintColours, View, cap

if TYPE_CHECKING:
    from discord import Embed, File, InteractionMessage, Member, SelectOption, User

    from helper_bot import NotGDKID
    from utils import BusStopResponse, NGKContext, PostgresPool, RouteData, StopInfo, TripData

    T = TypeVar("T")
    Interaction = discord.Interaction[NotGDKID]
    TripField = List[TripData] | TripData | Dict[Literal["Trip"], List[TripData]] | Dict[Literal["Trip"], TripData]
    TripFetcher = Callable[[str], Coroutine[Any, Any, BusStopResponse]]
    EditFunc = Callable[..., Coroutine[Any, Any, InteractionMessage]]
    RouteCollection = List[Tuple[str, str, List[TripData]]]

    route_colour_cache: Dict[str, Tuple[str, str]]

log = logging.getLogger(f"NotGDKID:{__name__}")

RAIL = ("1",)
LRT_STATION_HINTS = (
    "O-TRAIN",
    "PARLIAMENT",
)

RELOAD_FAIL = "i couldn't reload that page, it's most likely that there were no trips left, therefore i've reset the menu to the landing page"
PLACEHOLDER_URL = "https://i.vgy.me/x66JRh.png"

STN_PATTERN = re.compile(
    r"""
    # matches first set of a bus bay identifier (eg: South Keys [2A])
    # as well as an optional secondary paranthesized ID (eg: South Keys 2A [(B)])
    # reason why there are two formats is because OC Transpo is currently migrating to a simpler signage convention
    # so in the future, South Keys "stop 2A" will be renamed to simply "stop B"
    (?:
        (?:\s\d?[A-Z])
        |
        (?:\s\(\d?[A-Z]\))
    )+$

    |  # string terminates, OR

    # the station name suffix can also follow this particular format
    # string can terminate immediately, or can also contain a direction
    \sO-TRAIN(?:
        $
        |
        \s(?:WEST|EAST|NORTH|SOUTH)\s/\s(?:OUEST|EST|NORD|SUD)$
    )
    """,
    flags=re.ASCII | re.VERBOSE,
)

TITLECASE_PATTERN = re.compile(
    r"^(?P<start>\w)|(?:\s|-)d'(?P<d_apostrophe>\w)|\s(?P<normal_space>\w)|-(?P<dash>[^d'])|(?P<abbrev>(?:\w\.)+\w)",
    flags=re.ASCII,
)

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


def _slice(obj: List[T], /, *, size: int = 25) -> Tuple[List[T], ...]:
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


def _sort_routes(routes: List[RouteData], /) -> RouteCollection:
    return sorted(
        ((i["RouteHeading"], i["RouteNo"], _parse_trips(i["Trips"])) for i in routes),
        key=lambda x: int(x[1]) if x[1].isnumeric() else 0,
    )


FONT = ImageFont.truetype("assets/opensans.ttf", 72)
DEFAULT_ROUTE_COLOUR = ("E6E6E6", "58595B")


def _generate_route_icon(route: str, /) -> Coroutine[Any, Any, File]:
    def runner():
        bg_colour, text_colour = route_colour_cache.get(route, DEFAULT_ROUTE_COLOUR)

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
    if not view.departure_board_selected and view.sorting is Sorting.ROUTE:
        attachments = [await _generate_route_icon(view.current_key.split(":")[-1])]
    elif not view.departure_board_selected:
        attachments = [discord.File("assets/penis.png")]
    else:
        attachments = []

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


class BusDisplay(View, auto_defer=False, metaclass=AsyncInit):
    if TYPE_CHECKING:
        _destinations: Tuple[List[str], ...]
        _routes: Tuple[List[Tuple[str, str]], ...]

        def __await__(self):
            return self.__init__.__await__

    TIMEOUT = 120
    pages: Dict[str, Embed] = {}
    group: int = 0
    departure_page: int = 0
    sorting: Sorting = Sorting.ROUTE

    async def __init__(
        self,
        *,
        data: BusStopResponse,
        db: PostgresPool,
        owner: User | Member,
        trip_fetcher: TripFetcher,
        skip_components: bool = False,
    ):
        assert data["Routes"]["Route"] is not None
        trips, routes_raw = _get_trips_and_routes(data["Routes"]["Route"])

        destinations = _sort_destinations(trips)
        routes = _sort_routes(routes_raw)

        super().__init__(timeout=self.TIMEOUT)

        query = "SELECT * FROM stops WHERE stop_code = $1"
        self._stop_info: StopInfo = await db.fetchrow(query, data["StopNo"])  # type: ignore

        self._owner = owner
        self._data = data
        self._db = db
        self._destinations = _slice(destinations)
        self._destination_count = len(destinations)
        self._trip_fetcher = trip_fetcher

        spoof = [("", "")]  # spoof item, this will be the select option for the departure board
        self._routes = _slice(spoof + [r[:2] for r in routes])
        self._route_count = len(routes)

        self.current_key = "r::0"  # departure board page 1

        self._build_route_pages(routes)
        self._build_departure_board_pages(routes)
        self._build_destination_pages(destinations)
        if not skip_components:
            self.update_components()

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

    def reconfigure_with_key(self, key: str, /) -> None:
        self.current_key = key
        if key.startswith("d:"):
            self.sorting = Sorting.DEST
            self.swap_sorting.label = "Sort by route"
        else:
            self.sorting = Sorting.ROUTE
            self.swap_sorting.label = "Sort by destination"

        if self.departure_board_selected:
            group_count = len(self.collection)
            self.departure_page = int(key.split(":")[-1])
            self.group = min(self.departure_page, group_count - 1)
            self.current_key = f"r::{self.departure_page}"

    @property
    def collection(self) -> Tuple[List[str], ...] | Tuple[List[Tuple[str, str]], ...]:
        return self._routes if self.sorting is Sorting.ROUTE else self._destinations

    @property
    def collection_length(self) -> int:
        return self._route_count if self.sorting is Sorting.ROUTE else self._destination_count

    @property
    def departure_board_selected(self) -> bool:
        return "::" in self.current_key  # checking for no headsign, the delimiters would then be back-to-back

    def _make_custom_id(self) -> str:
        return f"★;{self._stop_info['stop_code']};{self.current_key};{round(time.time())}"

    def _add_trip_fields_to_embed(self, embed: Embed, /, *, trips: List[TripData]) -> None:
        for i, trip in enumerate(trips[:3], start=1):
            name = f"Trip {i}"
            if i > len(trips):
                embed.add_field(name=name, value="No data")
                continue

            cums_at = round((datetime.now() + timedelta(minutes=int(trip["AdjustedScheduleTime"]))).timestamp())

            arrives = f"**<t:{cums_at}:R>**"
            gps = f"GPS-adjusted? {BotEmojis.NO}"
            last_adjusted = "Last updated - N/A"

            assert embed.footer.text is not None
            if "destination" in embed.footer.text:
                mid = f"__Via Route__\n**`{trip['RouteNo']} {trip['TripDestination']}`**"
            else:
                mid = f"__Destination__\n**`{trip['TripDestination']}`**"

            if trip["AdjustmentAge"] != "-1":
                gps = f"GPS-adjusted? {BotEmojis.YES}"
                last_adjusted = f"Updated {round(60*float(trip['AdjustmentAge']))}s ago"

            last_trip = f"Last trip? - {BotEmojis.YES if trip['LastTripOfSchedule'] else BotEmojis.NO}"
            embed.add_field(name=name, value=f"{arrives}\n\n{mid}\n\n{last_adjusted}\n{gps}\n{last_trip}\n\u200b")

    def _build_next_three_embed(self, item: str, value: str, /, *, route_no: str | None = None) -> Embed:
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
            e.url = PLACEHOLDER_URL

        return e

    def _board_handle_tripdata(self, trip: TripData, first_trip_processed: int, /) -> str:
        s = " & " if first_trip_processed else ""

        minutes = int(trip["AdjustedScheduleTime"])
        if trip["AdjustmentAge"] != "-1" and minutes < 60:
            to_add = f"**{minutes}***" if minutes > 1 else BotEmojis.BUS_FLASHING

        elif minutes >= 60:
            cums_at = datetime.now() + timedelta(minutes=minutes)
            to_add = cums_at.strftime("%H:%M")

        else:  # scheduled in under an hour, no gps tracking available
            to_add = trip["AdjustedScheduleTime"]

        return s + (f"__{to_add}__" if trip["LastTripOfSchedule"] else to_add)

    def _make_board_description(self, chunk: RouteCollection, max_length: int, /) -> str:
        HEADSIGN_CAP = 19  # total 20, but excluding the space between the number and destination

        description_lines = []
        for headsign, route_no, trips in chunk:
            dest_cap = HEADSIGN_CAP - max_length
            num = format(route_no, f">{max_length}")
            text = format(cap(headsign, dest_cap), f"<{dest_cap}")
            line = f"**`{num} `**`{text}` - "

            # since we're only ever processing 2 objects at once, the index counter will only ever be 0 or 1
            # so we can use it as if it were a bool in an if statement, hence the naming
            for first_trip_processed, trip in enumerate(trips[:2]):
                time = self._board_handle_tripdata(trip, first_trip_processed)
                line += time  # gross this looks ugly

                # emojis also have colons, we don't want that
                if ":" in time and "<" not in time:
                    break

            description_lines.append(line)

        return "\n".join(description_lines)

    def _build_departure_board_pages(self, routes: RouteCollection, /) -> None:
        ROUTES_PER_PAGE = 20

        sliced_routes = _slice(routes, size=ROUTES_PER_PAGE)
        self._departure_page_count = len(sliced_routes)
        for idx, chunk in enumerate(sliced_routes):
            key = f"r::{idx}"

            rn = datetime.now()
            max_route_length = len(max(chunk, key=lambda x: len(x[1]))[1])
            desc = self._make_board_description(chunk, max_route_length)
            e = discord.Embed(title="All upcoming departures", description=desc, url=PLACEHOLDER_URL, timestamp=rn)
            e.set_author(name=f"Departure Board - {self._stop_info['stop_name']} [#{self._stop_info['stop_code']}]")
            e.set_footer(text=f"Page {idx + 1}/{len(sliced_routes)}")
            self.pages[key] = e

    def _build_route_pages(self, routes: RouteCollection, /) -> None:
        for headsign, route_no, trips in routes:
            key = f"r:{headsign}:{route_no}"

            fullroute = f"[{route_no}] {headsign}"
            term = "line" if route_no in RAIL else "route"
            e = self._build_next_three_embed(term, fullroute, route_no=route_no)
            self._add_trip_fields_to_embed(e, trips=trips)
            self.pages[key] = e

    def _build_destination_pages(self, destinations: List[str], /) -> None:
        assert self._data["Routes"]["Route"] is not None

        for dest in destinations:
            key = f"d:{dest}"

            e = self._build_next_three_embed("destination", dest)
            trips = sorted(
                (t for t in _get_trips_and_routes(self._data["Routes"]["Route"])[0] if t["TripDestination"] == dest),
                key=lambda x: int(x["AdjustedScheduleTime"]),
            )[:3]

            self._add_trip_fields_to_embed(e, trips=trips)
            self.pages[key] = e

    def _count_shown(self, *, group_index: int, group_size: int = 25) -> str:
        offset = 1 if not group_index else 0
        start = group_size * group_index + offset
        total = self.collection_length
        stop = min(total, group_size * (group_index + 1) - offset) if total >= group_size else total

        return f"{start}-{stop} of {total}"

    @property
    def _bus_route_opts(self) -> List[SelectOption]:
        get_term = lambda n: "Bus route" if n not in RAIL else "LRT line"

        opts = [
            discord.SelectOption(label=f"[{n}] {h}", value=f"r:{h}:{n}", description=get_term(n))
            for (h, n) in self._routes[self.group]  # (route headsign, route number)
            if h and f"r:{h}:{n}" != self.current_key or not h and not self.departure_board_selected
        ]

        # no headsign aka departure board option
        if not self.departure_board_selected and not self._routes[self.group][0][0]:
            opts[0].value = f"r::{self.departure_page}"
            opts[0].label = "View departure board"
            opts[0].description = "Click/Tap to view"

        return opts

    @property
    def _destination_opts(self) -> List[SelectOption]:
        return [
            discord.SelectOption(label=dest, value=f"d:{dest}", description="Destination")
            for dest in self._destinations[self.group]
            if f"d:{dest}" != self.current_key
        ]

    def _prepare_select(self) -> None:
        item = "Bus routes" if self.sorting is Sorting.ROUTE else "Destinations"
        opts = self._bus_route_opts if self.sorting is Sorting.ROUTE else self._destination_opts

        self.mode_entity_select.placeholder = f"{item} [{self._count_shown(group_index=self.group)}]"
        self.mode_entity_select.disabled = not bool(opts)

        self.mode_entity_select.options = opts or [discord.SelectOption(label="suck my balls")]

    def update_components(self) -> None:
        # condition only matters if the departure board is being displayed, hence this shorthand
        if_dep_board: Callable[[bool], bool] = lambda c: c if self.departure_board_selected else True

        self.children[0].custom_id = self._make_custom_id()
        self.previous_25.disabled = self.group == 0 and if_dep_board(self.departure_page == 0)
        self.next_25.disabled = self.group >= len(self.collection) - 1 and if_dep_board(
            self.departure_page >= self._departure_page_count - 1
        )

        idx, size = (self.departure_page, 20) if self.departure_board_selected else (self.group, 25)
        self.shown_counter.label = self._count_shown(group_index=idx, group_size=size)
        self._prepare_select()

    # <-- actual components now lmfao -->

    @ui.button(label="❮", row=0, disabled=True, custom_id="prev25")
    async def previous_25(self, interaction: Interaction, item: ui.Button):
        if self.group > 0:
            self.group -= 1

        if self.departure_board_selected and self.departure_page > 0:
            self.departure_page -= 1
            self.current_key = f"r::{self.departure_page}"

        self.update_components()
        kwargs = await _view_edit_kwargs(self)
        await interaction.extras["editor"](**kwargs)

    @ui.button(row=0, disabled=True, custom_id="counter")
    async def shown_counter(self, interaction: Interaction, item: ui.Button):
        await interaction.response.defer()

    @ui.button(label="❯", row=0, disabled=True, custom_id="next25")
    async def next_25(self, interaction: Interaction, item: ui.Button):
        if self.group < len(self.collection) - 1:
            self.group += 1

        if self.departure_board_selected and self.departure_page < self._departure_page_count - 1:
            self.departure_page += 1
            self.current_key = f"r::{self.departure_page}"

        self.update_components()
        kwargs = await _view_edit_kwargs(self)
        await interaction.extras["editor"](**kwargs)

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
        self._destination_count = len(destinations)

        spoof = [("", "")]  # spoof item, this will be the select option for the departure board
        self._routes = _slice(spoof + [r[:2] for r in routes])
        self._route_count = len(routes)

        self.pages = {}
        self._build_route_pages(routes)
        self._build_departure_board_pages(routes)
        self._build_destination_pages(destinations)

        page = self.pages.get(self.current_key, None)
        if not page:
            self.current_key = "r::0"  # departure board first page
            self.sorting = Sorting.ROUTE
            self.departure_page = 0

            await interaction.followup.send(RELOAD_FAIL, ephemeral=True)

        self.update_components()
        kwargs = await _view_edit_kwargs(self)
        await interaction.edit_original_response(**kwargs)

    @ui.select(row=1, custom_id="selector")
    async def mode_entity_select(self, interaction: Interaction, item: ui.Select):
        key = item.values[0]
        self.current_key = key

        self.departure_page = 0

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
            self.sorting = Sorting.ROUTE
            self.current_key = "r::0"
            self.departure_page = 0

            new_label = "Sort by destination"

        self.group = 0
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

        modal = NewLookupModal(og_view=self, db=self._db, trip_fetcher=self._trip_fetcher)
        await interaction.response.send_modal(modal)


class ResultSelector(View, auto_defer=True):
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
        view = await BusDisplay(
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

        modal = NewLookupModal(og_view=self._og_view, db=self._db, trip_fetcher=self._trip_fetcher)
        await interaction.response.send_modal(modal)


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
            view = await BusDisplay(
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

    @cached_property
    def item_indexes(self) -> Dict[str, int]:
        indexes = {}
        for member in BusDisplay.__dict__.values():
            if hasattr(member, "__discord_ui_model_kwargs__"):
                indexes[member.__discord_ui_model_kwargs__["custom_id"]] = len(indexes)

        return indexes

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        if (
            not interaction.message
            or not interaction.message.components
            or not interaction.message.interaction
            or not interaction.data
            or "recieved" in interaction.extras
            or "custom_id" not in interaction.data
            or interaction.response.is_done()
            or interaction.type is not discord.InteractionType.component
        ):
            return

        if self.client.is_blacklisted(interaction.user):
            return await interaction.response.send_message("you're blacklisted \N{CLOWN FACE}", ephemeral=True)

        items = interaction.message.components
        first = items[0].children[0] if isinstance(items[0], discord.ActionRow) else items[0]

        assert first.custom_id is not None
        if not first.custom_id.startswith("★"):
            return

        stop_code, current_key, last_active_str = first.custom_id.split(";")[-3:]

        view_expired = int(last_active_str) + BusDisplay.TIMEOUT < time.time()
        bot_restarted = int(last_active_str) < self.client.uptime.timestamp() < int(last_active_str) + BusDisplay.TIMEOUT
        if not view_expired and not bot_restarted:
            # the view hasn't yet expired; handle interaction check in there
            return

        if interaction.user.id != interaction.message.interaction.user.id:
            return await interaction.response.send_message(random.choice(CHOICES), ephemeral=True)

        custom_id = interaction.data["custom_id"]
        child_idx = 0 if custom_id.startswith("★") else self.item_indexes[custom_id]

        interaction.extras["sender"] = interaction.followup.send
        interaction.extras["editor"] = interaction.edit_original_response
        if child_idx == 6:
            # we can only send modals in responses, so we've gotta do it here
            modal = NewLookupModal(db=self.client.db, trip_fetcher=self.fetch_trips)
            return await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer()

        try:
            new_data = await self.fetch_trips(stop_code)
        except OCTranspoError as e:
            return await interaction.followup.send(embed=e.display, ephemeral=True)
        except BadResponse as e:
            return await interaction.followup.send(f"{str(e)}\n```json\n{e.raw!r}```", ephemeral=True)

        assert new_data["Routes"]["Route"] is not None
        view = await BusDisplay(
            data=new_data, db=self.client.db, owner=interaction.user, trip_fetcher=self.fetch_trips, skip_components=True
        )

        page = view.pages.get(current_key, None)
        if page is not None:
            view.reconfigure_with_key(current_key)

        elif child_idx == 4:
            # page wasn't found, and the select's callback would then raise an error
            # so let's "pretend" we pressed refresh instead hehe
            child_idx = 3

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

    @staticmethod
    def title(s: str):
        def handle_match(m: re.Match[str]) -> str:
            subber = next(filter(lambda x: x, m.groups()))
            return m.group().replace(subber, subber.upper())

        return (
            TITLECASE_PATTERN.sub(handle_match, s.lower())
            .replace("Uottawa", "uOttawa")
            .replace("H.s", "H.S")
            .replace("R.r", "R.R")
            .replace("Td ", "TD ")
            .replace("Ey ", "EY ")
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

    def _parse_csv_line(self, row: List[str], /, columns: Tuple[str, ...], colindexes: Tuple[int, ...]) -> List[str]:
        filtered = [row[i] for i in colindexes]

        # special casing for the stops table, for transitway stations
        # essentially there are separate records of all the individual bus stands at a station that all share one stop code
        # that are all being amalgamated into one single entity

        if "stop_name" in columns:
            i = columns.index("stop_name")
            if "/" not in filtered[i] or any(n in filtered[i] for n in LRT_STATION_HINTS):
                filtered[i] = STN_PATTERN.sub(" stn.", filtered[i], count=1)

            filtered[i] = self.title(filtered[i])

        # special casing for the routes table, just caches it right here right now

        elif "route_short_name" in columns:
            global route_colour_cache
            route_colour_cache[filtered[0]] = tuple(filtered[1:])  # type: ignore

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

        # caching routes
        if "route_short_name" in columns:
            global route_colour_cache
            route_colour_cache.clear()

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
        view = await BusDisplay(
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
        term = "line" if route in RAIL else "route"

        embed = discord.Embed(title=f"Route map for {term} {route}", url=title_url).set_image(url=url)
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
