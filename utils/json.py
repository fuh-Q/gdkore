"""
Original from RoboDanny, source below

https://github.com/Rapptz/RoboDanny/blob/28f41d0371d0caffa524a0db8dca061c44a8b946/cogs/utils/config.py
"""

import orjson
import os
from typing import Any, Callable, Dict, Generic, TypeVar, overload
import uuid
import asyncio

T = TypeVar("T")

ObjectHook = Callable[[Dict[str, Any]], Any]


class Config(Generic[T]):
    """The "database" object. Internally based on `json`."""

    def __init__(
        self,
        name: str,
        *,
        load_later: bool = False,
    ):
        self.name = name
        self.loop = asyncio.get_running_loop()
        self.lock = asyncio.Lock()
        self._db: Dict[str, T | Any] = {}
        if load_later:
            self.loop.create_task(self.load())
        else:
            self.load_from_file()

    def load_from_file(self):
        try:
            with open(self.name, "rb") as f:
                self._db = orjson.loads(f.read())
        except FileNotFoundError:
            self._db = {}

    async def load(self):
        async with self.lock:
            await self.loop.run_in_executor(None, self.load_from_file)

    def _dump(self):
        temp = f"{uuid.uuid4()}-{self.name.replace('/', '-')}.tmp"
        with open(temp, "wb") as tmp:
            tmp.write(orjson.dumps(self._db.copy(), option=orjson.OPT_INDENT_2))

        # atomically move the file
        os.replace(temp, self.name)

    async def save(self) -> None:
        async with self.lock:
            await self.loop.run_in_executor(None, self._dump)

    @overload
    def get(self, key: Any) -> T | None:
        ...

    @overload
    def get(self, key: Any, default: Any) -> T:
        ...

    def get(self, key: Any, default: Any = None) -> T | None:
        return self._db.get(str(key), default)

    async def put(self, key: Any, value: T | Any) -> None:
        self._db[str(key)] = value
        await self.save()

    async def remove(self, key: Any, *, missing_ok: bool = False) -> None:
        try:
            del self._db[str(key)]
            await self.save()
        except KeyError as e:
            if missing_ok:
                return
            else:
                raise e

    async def migratekey(self, key: Any, new_key: Any) -> None:
        self._db[str(new_key)] = self.get(key)
        await self.save()

    def __contains__(self, item: Any) -> bool:
        return str(item) in self._db

    def __getitem__(self, item: Any) -> T | Any:
        return self._db[str(item)]

    def __len__(self) -> int:
        return len(self._db)

    def get_all(self) -> Dict[str, T | Any]:
        return self._db.copy()
