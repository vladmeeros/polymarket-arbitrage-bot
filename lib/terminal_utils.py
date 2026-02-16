from datetime import datetime
from collections import deque
from dataclasses import dataclass, field


class Colors:
    BLACK = "\033[30m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"
    SUCCESS = "\033[92m"
    WARNING = "\033[93m"
    ERROR = "\033[91m"
    INFO = "\033[94m"
    TRADE = "\033[95m"


LOG_SYMBOLS = {
    "info": ("i", Colors.BLUE),
    "success": ("+", Colors.GREEN),
    "warning": ("!", Colors.YELLOW),
    "error": ("x", Colors.RED),
    "trade": ("$", Colors.MAGENTA),
    "debug": (".", Colors.DIM),
}


def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str, level: str = "info", show_timestamp: bool = True) -> str:
    formatted = format_log(msg, level, show_timestamp)
    print(formatted)
    return formatted


def format_log(msg: str, level: str = "info", show_timestamp: bool = True) -> str:
    symbol, color = LOG_SYMBOLS.get(level, (".", ""))
    ts = get_timestamp()
    if show_timestamp:
        return f"{Colors.CYAN}[{ts}]{Colors.RESET} {color}{symbol}{Colors.RESET} {msg}"
    return f"{color}{symbol}{Colors.RESET} {msg}"


def clear_screen() -> None:
    print("\033[2J\033[H", end="", flush=True)


def move_cursor_home() -> None:
    print("\033[H", end="", flush=True)


def clear_and_print(lines: list) -> None:
    output = "\033[H\033[J" + "\n".join(lines)
    print(output, flush=True)


def format_price(price: float, width: int = 9) -> str:
    return f"{price:>{width}.4f}"


def format_size(size: float, width: int = 9) -> str:
    return f"{size:>{width}.1f}"


def format_pnl(pnl: float, include_sign: bool = True) -> str:
    color = Colors.GREEN if pnl >= 0 else Colors.RED
    if include_sign:
        return f"{color}${pnl:+.2f}{Colors.RESET}"
    return f"{color}${abs(pnl):.2f}{Colors.RESET}"


def format_countdown(minutes: int, seconds: int) -> str:
    if minutes < 0:
        return "--:--"
    total_secs = minutes * 60 + seconds
    if total_secs <= 0:
        return f"{Colors.RED}ENDED{Colors.RESET}"
    elif total_secs <= 60:
        color = Colors.RED
    elif total_secs <= 180:
        color = Colors.YELLOW
    else:
        color = Colors.GREEN
    return f"{color}{minutes:02d}:{seconds:02d}{Colors.RESET}"


@dataclass
class LogBuffer:
    max_size: int = 5
    messages: deque = field(default_factory=lambda: deque(maxlen=5))

    def __post_init__(self):
        self.messages = deque(maxlen=self.max_size)

    def add(self, msg: str, level: str = "info") -> None:
        formatted = format_log(msg, level, show_timestamp=True)
        self.messages.append(formatted)

    def get_messages(self) -> list:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()


class StatusDisplay:
    def __init__(self, width: int = 80):
        self.width = width
        self.lines: list = []

    def add_line(self, line: str) -> "StatusDisplay":
        self.lines.append(line)
        return self

    def add_header(self, text: str) -> "StatusDisplay":
        self.lines.append(f"{Colors.BOLD}{text}{Colors.RESET}")
        return self

    def add_separator(self, char: str = "-") -> "StatusDisplay":
        self.lines.append(char * self.width)
        return self

    def add_bold_separator(self, char: str = "=") -> "StatusDisplay":
        self.lines.append(f"{Colors.BOLD}{char * self.width}{Colors.RESET}")
        return self

    def add_blank(self) -> "StatusDisplay":
        self.lines.append("")
        return self

    def render(self, in_place: bool = True) -> str:
        output = "\n".join(self.lines)
        if in_place:
            print("\033[H\033[J" + output, flush=True)
        else:
            print(output, flush=True)
        return output

    def clear(self) -> "StatusDisplay":
        self.lines = []
        return self

    def get_lines(self) -> list:
        return self.lines.copy()
