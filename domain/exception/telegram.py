from enum import Enum, auto


class TelegramExceptions(Enum):
    RetryAfter = auto()  # 1
    TimedOut = auto()  # 2
    Forbidden = auto()  # 3
    TelegramError = auto()  # 4
    Other = auto()  # 5
