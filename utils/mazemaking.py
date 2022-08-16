from __future__ import annotations
import io

import random
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw

from .enums import BlockTypes

# fmt: off


class _MazeBlock:
    __slots__ = ("_x", "_y", "_block_type", "_frozen")

    def __init__(self, x, y, block_type):
        self._x = x
        self._y = y
        self._block_type = block_type
        self._frozen = False

        if self._x % 2 == 1 and self._y % 2 == 1:
            self._frozen = True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} xy={(self._x, self._y)} type={self._block_type}>"


class Maze:
    """
    Maze maker thingy yes yes
    """
    
    __slots__ = ("_width", "_height", "_blocks", "_special_spaces", "_sets")

    def __init__(
        self,
        width: int,
        height: int,
        blocks: List | None = None,
        specials: List | None = None,
    ) -> None:
        self._width = width
        self._height = height
        self._blocks = blocks or []
        self._special_spaces = specials or []

        if not self._blocks:
            for y in range(height):
                for x in range(width):
                    path = y % 2 == 0 and x % 2 == 0

                    self._blocks.append(
                        _MazeBlock(x, y, BlockTypes.PATH if path else BlockTypes.WALL)
                    )
            self._sets = {block: set() for block in self._blocks}

            self._make_maze()
            self._pick_special_spaces()
    
    def _ram_cleanup(self):
        del (self._width,
             self._height,
             self._blocks,
             self)
    
    @classmethod
    def from_db(cls, blocks: List[Dict[str, int]], specials: List[List[int]], width: int, height: int) -> Maze:
        blocks = [_MazeBlock(bl["x"], bl["y"], BlockTypes.PATH
                  if bl["type"] else BlockTypes.WALL)
                  for bl in blocks]
        
        return cls(width, height, blocks, specials)

    def to_image(
        self,
        path_rgb: Tuple[int],
        wall_rgb: Tuple[int],
        finish_icon: bytes | None
    ) -> Image.Image:
        img = Image.new("RGBA", (self._width * 22, self._height * 22), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        rows = [self._blocks[i:i + self._width] for i in range(0, len(self._blocks), self._width)]

        for row in rows:
            for bl in row:
                if bl._block_type is BlockTypes.PATH:
                    x2 = (x1 := bl._x * 20) + 35
                    y2 = (y1 := bl._y * 20) + 35
                    
                    draw.rectangle((
                        (x1, y1),
                        (x2, y2)
                    ), fill=path_rgb)
                    
                    if bl is self._blocks[-1]:
                        if not finish_icon:
                            #bigger = max(path_rgb, wall_rgb)
                            #contrast_value = max(bigger) + min(bigger)
                            #op = int.__sub__ if contrast_value > 122 else int.__add__
                            #draw.ellipse((
                            #    (x1 + 1, y1 + 1),
                            #    (x2 - 1, y2 - 1)
                            #), fill=tuple(map(lambda i: op(contrast_value, i), bigger)))
                            finish_icon = Image.open("assets/trash.png")
                        else:
                            finish_icon = Image.open(io.BytesIO(finish_icon)).convert("RGBA")
                        img.paste(
                            finish_icon,
                            (x1, y1),
                            finish_icon
                        )
                        finish_icon.close()
                        del finish_icon
                        
                        img = img.crop((0, 0, x2, y2))
        
        with Image.new(
            "RGB",
            (int(img.width + 10), int(img.height + 10)),
            wall_rgb
        ) as base:
            base.paste(
                img,
                (int((base.width - img.width) / 2), int((base.height - img.height) / 2)),
                img
            )

        img.close()
        del img, draw, rows
        return base

    def _make_maze(self):
        while not all(
            len(item_set) == len(self._sets[self._blocks[0]]) and len(item_set) > 0
            for item, item_set in self._sets.items()
            if item._block_type is BlockTypes.PATH
        ):
            wall = self._get_random_wall()
            wall_neighbours = self._get_neighbours(wall)
            before, after = wall_neighbours
            chunk = [before, wall, after]

            if self._same_set(before, after):
                continue

            for item in wall_neighbours:
                for i in chunk:
                    self._sets[item].add(i)
                for i in list(self._sets[item]):
                    self._sets[i].update(self._sets[item])
                item._frozen = True

            wall._block_type = BlockTypes.PATH
            wall._frozen = True
    
        del self._sets
    
    def _pick_special_spaces(self):
        choices = [
            bl
            for bl in self._blocks[1:-1]
            if bl._block_type is not BlockTypes.WALL
            and bl._x % 2 == 0 and bl._y % 2 == 0
        ]
        
        coords = lambda: [(c := random.choice(choices))._x, c._y]
        
        if len(self._blocks) >= 120:
            spaces = [coords() for _ in range(len(self._blocks) // 120)]
        else:
            spaces = [coords()]
        
        self._special_spaces = spaces

    def _same_set(self, before, after):
        return not self._sets[after].isdisjoint(self._sets[before])

    def _get_neighbours(self, wall):
        up = self._get_block(wall._x, wall._y - 1)
        down = self._get_block(wall._x, wall._y + 1)
        left = self._get_block(wall._x - 1, wall._y)
        right = self._get_block(wall._x + 1, wall._y)
        checker = up if up is not None else down

        if checker._block_type is BlockTypes.WALL:
            return [left, right]
        else:
            return [up, down]

    def _get_block(self, x, y):
        for bl in self._blocks:
            if bl._x == x and bl._y == y:
                return bl

    def _get_random_wall(self):
        choice = random.choice([
            bl
            for bl in self._blocks
            if bl._block_type is not BlockTypes.PATH and not bl._frozen
        ])

        return choice
