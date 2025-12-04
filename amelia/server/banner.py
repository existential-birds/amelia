"""ASCII banner with gradient colors for server startup including an airplane."""
from rich.console import Console
from rich.style import Style
from rich.text import Text


# --- Color Palette ---
NAVY = "#0a2463"
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
    """Interpolate between two hex colors.

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
    """Generate ASCII banner with horizontal gradient using specific colors.

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


def print_banner(console: Console) -> None:
    """Print the gradient ASCII banner.

    Args:
        console: Rich Console instance to print to.
    """
    # Using NAVY (#0a2463) to GOLD (#ffc857) for a "Sky/Sunrise" effect
    banner = get_gradient_banner(start_color=NAVY, end_color=GOLD)
    
    console.print() 
    console.print(banner)
    console.print()