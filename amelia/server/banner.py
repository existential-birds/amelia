"""ASCII banner with gradient colors for server startup including an airplane."""
import random

from rich.console import Console
from rich.style import Style
from rich.text import Text


# --- Color Palette ---
NAVY = "#0a2463"
TWILIGHT = "#1245ba"
RUST = "#a0311c"
GOLD = "#ffc857"
CREAM = "#eff8e2"
GRAY = "#6d726a"
MOSS = "#88976b"
DARK_GREEN = "#1f332e"

# --- ASCII Art ---
# Combined plane and text for unified gradient handling
# The plane is a stylized twin-engine (nod to the Electra)
BANNER_ART = """\
              DO-O        
          __|__           
   --------(_)--------    
     O  O       O  O      
                          
  █████╗  ███╗   ███╗ ███████╗ ██╗      ██╗  █████╗
 ██╔══██╗ ████╗ ████║ ██╔════╝ ██║      ██║ ██╔══██╗
 ███████║ ██╔████╔██║ █████╗   ██║      ██║ ███████║
 ██╔══██║ ██║╚██╔╝██║ ██╔══╝   ██║      ██║ ██╔══██║
 ██║  ██║ ██║ ╚═╝ ██║ ███████╗ ███████╗ ██║ ██║  ██║
 ╚═╝  ╚═╝ ╚═╝     ╚═╝ ╚══════╝ ╚══════╝ ╚═╝ ╚═╝  ╚═╝"""


def _interpolate_color(color1: str, color2: str, factor: float) -> str:
    """Interpolate between two hex colors using linear interpolation.

    Args:
        color1: Starting hex color.
        color2: Ending hex color.
        factor: Interpolation factor (0.0 = color1, 1.0 = color2).

    Returns:
        Interpolated hex color string.
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


def get_gradient_banner(start_color: str, end_color: str) -> Text:
    """Generate ASCII banner with horizontal gradient from left to right.

    Args:
        start_color: The hex code for the left side of the gradient.
        end_color: The hex code for the right side of the gradient.

    Returns:
        Rich Text object with gradient-colored ASCII art.
    """
    lines = BANNER_ART.split("\n")
    text = Text()

    # Find max line length to ensure gradient is distributed evenly 
    # regardless of line width (prevents "skewing" of the color ramp)
    max_len = max(len(line) for line in lines)

    for i, line in enumerate(lines):
        for j, char in enumerate(line):
            if char.strip():  # Only color non-whitespace
                # Calculate gradient position (0.0 to 1.0) based on horizontal position
                factor = j / max_len if max_len > 0 else 0
                color = _interpolate_color(start_color, end_color, factor)
                text.append(char, style=Style(color=color))
            else:
                text.append(char)
        if i < len(lines) - 1:
            text.append("\n")

    return text


def get_agi_banner() -> Text:
    """Generate the AGI countdown banner with gradient styling.

    Uses a random countdown value between 14 and 1000 days.

    Returns:
        Rich Text object with the styled AGI countdown banner.
    """
    days_until_agi = random.randint(14, 1000)
    inner_width = 39
    centered_days = str(days_until_agi).center(inner_width)

    lines = [
        "    ╔═══════════════════════════════════════╗",
        "    ║                                       ║",
        "    ║   DAYS REMAINING UNTIL AGI ACHIEVED:  ║",
        f"    ║{centered_days}║",
        "    ║                                       ║",
        "    ╚═══════════════════════════════════════╝",
    ]

    text = Text()
    max_len = max(len(line) for line in lines)

    for i, line in enumerate(lines):
        for j, char in enumerate(line):
            if char.strip():
                factor = j / max_len if max_len > 0 else 0
                color = _interpolate_color(GOLD, MOSS, factor)
                text.append(char, style=Style(color=color))
            else:
                text.append(char)
        if i < len(lines) - 1:
            text.append("\n")

    return text


def get_service_urls_display(
    api_host: str,
    api_port: int,
    is_dev_mode: bool,
) -> Text:
    """Generate styled display of service URLs for dashboard and API.

    Args:
        api_host: Host the API is bound to.
        api_port: Port the API is bound to.
        is_dev_mode: Whether running in dev mode (separate Vite server).

    Returns:
        Rich Text object with styled service URLs.
    """
    # Use localhost for display if bound to 0.0.0.0
    display_host = "localhost" if api_host == "0.0.0.0" else api_host
    api_url = f"http://{display_host}:{api_port}"

    # In dev mode, dashboard runs on Vite (port 5173)
    # In user mode, dashboard is served from API server
    dashboard_url = "http://localhost:5173" if is_dev_mode else api_url

    text = Text()

    # Dashboard line with arrow
    text.append("    ➜ ", style=MOSS)
    text.append("Dashboard: ", style=CREAM)
    text.append(dashboard_url, style=f"bold {GOLD}")
    text.append("\n")

    # API line (only show separately in dev mode where they differ)
    if is_dev_mode:
        text.append("    ➜ ", style=MOSS)
        text.append("API:       ", style=CREAM)
        text.append(api_url, style=f"bold {CREAM}")

    return text


def print_banner(console: Console) -> None:
    """Print the gradient ASCII banner with AGI countdown to console.

    Args:
        console: Rich Console instance to print to.
    """
    # Using NAVY (#0a2463) to GOLD (#ffc857) for a "Sky/Sunrise" effect
    banner = get_gradient_banner(start_color=NAVY, end_color=GOLD)

    console.print()
    console.print(banner)
    console.print()
    console.print(get_agi_banner())
    console.print()
