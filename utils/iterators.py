import asyncio
import json
from typing import Any, Callable, Dict, List, Tuple


class GoogleChunker:
    """
    Async iterator to split the Google data fetch into multiple chunks.
    
    This allows displaying a smaller chunk of data to the user while the rest
    loads in the background, for faster initial loading times.
    
    Parameters
    ----------
    loop: `asyncio.AbstractEventLoop`
        An event loop object.
    google_func: `Callable[[Any | None], Any]`
        The callback to execute that fetches data from Google.
    *args: `Tuple[Any]`
        Any extra arguments to pass onto the callback
    
    Note
    ----
    The callback `MUST` take a `nextPageToken` parameter as its first argument. This can be set to `None` by default.
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        google_func: Callable[[Any | None], Any],
        next_page: str,
        *args: Tuple[Any],
    ):
        self.loop = loop
        self.func = google_func
        self.args = args
        
        self.next_page = next_page
        
        self._stop = False
    
    def __aiter__(self):
        return self
    
    async def __anext__(self) -> List[Dict]:
        if self._stop:
            raise StopAsyncIteration
        
        result = await self.loop.run_in_executor(
            None, self.func, self.next_page, *self.args
        )
        
        if not (next_page := result.get("nextPageToken", "")):
            self._stop = True

        self.next_page = next_page
        return result[tuple(result)[-1]]
