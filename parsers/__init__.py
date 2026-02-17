"""Site-specific parsers for Cafe24-based figure shops."""

from parsers.figurepresso import FigurepressoParser
from parsers.comicsart import ComicsArtParser
from parsers.maniahouse import ManiahouseParser
from parsers.rabbits import RabbitsParser
from parsers.ttabbaemall import TtabbaemallParser

PARSERS = {
    "figurepresso": FigurepressoParser,
    "comicsart": ComicsArtParser,
    "maniahouse": ManiahouseParser,
    "rabbits": RabbitsParser,
    "ttabbaemall": TtabbaemallParser,
}
