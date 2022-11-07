import time
from typing import Any, Generic, Tuple, TypeVar

KT = TypeVar("KT")
VT = TypeVar("VT")

class CappedDict(dict, Generic[KT, VT]):
    """
    Modified `dict` which removes the oldest item when a new item
    is inserted, once a specified cap is reached.

    Parameters
    ----------
    cap: `int`
        The size at which the dict will be maxed out at.
    """

    def __init__(self, cap: int):
        self.cap = cap

    def get(self, k: KT, default: Any | None = None) -> Any:
        super().get(k, default)

    def __setitem__(self, k: KT, v: VT) -> None:
        super().__setitem__(k, v)

        if len(self) > self.cap:
            del self[tuple(self)[0]]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

class ExpiringDict(dict, Generic[KT, VT]):
    """
    Modified `dict` in which items are removed after their respective timeouts
    have expired.

    Parameters
    ----------
    timeout: `int`
        The time in seconds that the items will remain before being removed.
    will_refresh: `bool`
        Whether or not to refresh an item's timeout when referenced from the mapping.
    """

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
