"""ASCII banner with gradient colors for server startup."""
from rich.console import Console
from rich.style import Style
from rich.text import Text


# Color palette from design mock
GOLD = "#FFC857"
GREEN = "#5B8A72"
TEXT_PRIMARY = "#EFF8E2"
TEXT_SECONDARY = "#88A896"

# ASCII art for AMELIA using large block font
AMELIA_ASCII = """\
  █████╗  ███╗   ███╗ ███████╗ ██╗      ██╗  █████╗
 ██╔══██╗ ████╗ ████║ ██╔════╝ ██║      ██║ ██╔══██╗
 ███████║ ██╔████╔██║ █████╗   ██║      ██║ ███████║
 ██╔══██║ ██║╚██╔╝██║ ██╔══╝   ██║      ██║ ██╔══██║
 ██║  ██║ ██║ ╚═╝ ██║ ███████╗ ███████╗ ██║ ██║  ██║
 ╚═╝  ╚═╝ ╚═╝     ╚═╝ ╚══════╝ ╚══════╝ ╚═╝ ╚═╝  ╚═╝"""


def _interpolate_color(color1: str, color2: str, factor: float) -> str:
    """Interpolate between two hex colors.

    Args:
        color1: Starting hex color (e.g., "#FFC857").
        color2: Ending hex color (e.g., "#5B8A72").
        factor: Interpolation factor (0.0 = color1, 1.0 = color2).

    Returns:
        Interpolated hex color.
    """
    # Parse hex colors
    r1 = int(color1[1:3], 16)
    g1 = int(color1[3:5], 16)
    b1 = int(color1[5:7], 16)

    r2 = int(color2[1:3], 16)
    g2 = int(color2[3:5], 16)
    b2 = int(color2[5:7], 16)

    # Interpolate
    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)

    return f"#{r:02x}{g:02x}{b:02x}"


def get_gradient_banner() -> Text:
    """Generate ASCII banner with horizontal gradient.

    Returns:
        Rich Text object with gradient-colored ASCII art.
    """
    lines = AMELIA_ASCII.split("\n")
    text = Text()

    # Find max line length for consistent gradient
    max_len = max(len(line) for line in lines)

    for i, line in enumerate(lines):
        for j, char in enumerate(line):
            if char.strip():  # Only color non-whitespace
                # Calculate gradient position (0.0 to 1.0) based on horizontal position
                factor = j / max_len if max_len > 0 else 0
                color = _interpolate_color(GOLD, GREEN, factor)
                text.append(char, style=Style(color=color))
            else:
                text.append(char)
        if i < len(lines) - 1:
            text.append("\n")

    return text


def print_banner(console: Console) -> None:
    """Print the gradient ASCII banner.

    Args:
        console: Rich Console instance to print to.
    """
    banner = get_gradient_banner()
    console.print(banner)
    console.print()  # Empty line after banner
