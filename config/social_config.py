"""
social_config.py — All social media post visual settings for The Currents.
Edit ONLY this file to change post appearance. No logic here.
"""

# ── Brand ─────────────────────────────────────────────────────────────────────
BRAND_TEXT          = "THE CURRENTS"

# ── Colors ────────────────────────────────────────────────────────────────────
COLOR_HEADLINE      = "#FFFFFF"      # Pure white
COLOR_BODY          = "#E8E8E8"      # Slightly off-white for body
COLOR_ACCENT        = "#E87722"      # Saffron-orange (divider line, source tag)
COLOR_BRAND         = "#AAAAAA"      # Subtle grey for branding

# ── Background ────────────────────────────────────────────────────────────────
BG_BLUR_RADIUS      = 1.2            # Gaussian blur on background (0 = sharp)

# ── Overlay ───────────────────────────────────────────────────────────────────
OVERLAY_START       = 0.30           # Gradient starts at 30% from top
OVERLAY_ALPHA_MAX   = 230            # Max alpha (0-255); 230 = very dark at bottom

# ── Text layout ───────────────────────────────────────────────────────────────
TEXT_PADDING_X      = 52             # px from left/right edge
TEXT_ZONE_TOP       = 0.50           # Text starts at 50% height from top

DIVIDER_THICKNESS   = 4              # px height of accent line
DIVIDER_GAP_ABOVE   = 18             # px gap between divider and headline

HEADLINE_LINE_SPACING = 8            # px between headline lines
CONTEXT_GAP_ABOVE     = 16           # px between headline and body text
BODY_LINE_SPACING     = 6            # px between body text lines

FOOTER_MARGIN_BOT   = 46             # px from bottom for source/branding

# ── Font sizes (px) ───────────────────────────────────────────────────────────
FONT_SIZE_HEADLINE  = 58
FONT_SIZE_BODY      = 32
FONT_SIZE_SOURCE    = 26
FONT_SIZE_BRAND     = 22

# ── Font paths (fallback chain) ────────────────────────────────────────────────
FONT_BOLD_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_REGULAR_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

# ── Circular inset image ──────────────────────────────────────────────────────
INSET_X             = 52             # px from left
INSET_Y             = 52             # px from top
INSET_DIAMETER      = 200            # px
INSET_BORDER_WIDTH  = 4              # px accent-color border

# ── Output quality ────────────────────────────────────────────────────────────
JPEG_QUALITY        = 92
