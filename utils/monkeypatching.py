import sys
from asyncio import Handle
from typing import Any, Callable

from discord.gateway import DiscordWebSocket


async def mobile(self: DiscordWebSocket):
    """
    `discord.py` override to allow for a mobile status on your bot.
    """
    payload = {
        "op": self.IDENTIFY,
        "d": {
            "token": self.token,
            "properties": {
                "os": sys.platform,
                "browser": "Discord iOS",
                "device": "discord.py",
            },
            "compress": True,
            "large_threshold": 250,
            "v": 3,
        },
    }

    if self.shard_id is not None and self.shard_count is not None:
        payload["d"]["shard"] = [self.shard_id, self.shard_count]

    state = self._connection
    if state._activity is not None or state._status is not None:
        payload["d"]["presence"] = {
            "status": state._status,
            "game": state._activity,
            "since": 0,
            "afk": False,
        }

    if state._intents is not None:
        payload["d"]["intents"] = state._intents.value

    await self.call_hooks("before_identify", self.shard_id, initial=self._initial_identify)
    await self.send_as_json(payload)


def new_call_soon(self: Any, callback: Callable[..., object], *args: Any, context=None) -> Handle:  # type: ignore
    """
    `asyncio` override to suppress the FUCKING ANNOYING error thrown on Windows.
    """
    if not self._closed:
        if self._debug:
            self._check_thread()
            self._check_callback(callback, "call_soon")
        handle = self._call_soon(callback, args, context)
        if handle._source_traceback:
            del handle._source_traceback[-1]
        return handle
