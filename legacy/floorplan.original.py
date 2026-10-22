
from io import BytesIO

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


SUPPORTED_ROOMS = {"bedroom", "living_room", "kitchen"}
VALID_DIRECTIONS = {"north", "east", "south", "west"}

FURNITURE_SIZES = {
    "bed": (1.6, 2.0),
    "single_bed": (1.0, 2.0),
    "wardrobe": (0.6, 1.8),
    "chair": (0.6, 0.6),
    "desk": (1.2, 0.6),
    "sofa": (2.0, 0.85),
    "table": (0.8, 0.8),
    "dining_table": (1.4, 0.9),
    "tv_unit": (1.4, 0.4),
    "counter": (0.6, 2.0),
    "stove": (0.6, 0.6),
    "refrigerator": (0.7, 0.7),
    "sink": (0.6, 0.6),
    "plant": (0.4, 0.4),
}

FURNITURE_COLORS = {
    "bed": "lightblue",
    "single_bed": "lightblue",
    "wardrobe": "wheat",
    "chair": "lightgreen",
    "desk": "lightyellow",
    "sofa": "lightblue",
    "table": "wheat",
    "dining_table": "wheat",
    "tv_unit": "lightgray",
    "counter": "lightgray",
    "stove": "salmon",
    "refrigerator": "lightcyan",
    "sink": "lightcyan",
    "plant": "lightgreen",
}

# Clockwise order around the room, starting from north.
DIRECTION_ORDER = ["north", "east", "south", "west"]


def create_floorplan(
    width: float = 4.0,
    length: float = 3.5,
    room_type: str = "bedroom",
    output_format: str = "png",
    placements: list[dict] | None = None,
    north_direction: str = "north",
) -> bytes:
    """
    Generate a preliminary floor plan from user-supplied dimensions
    and furniture coordinates.

    x and y are measured from the bottom-left corner of the drawing.
    Furniture coordinates are not rotated.

    north_direction specifies the real-world direction represented
    by the TOP edge of the drawing.
    """

    if not (2 <= width <= 15 and 2 <= length <= 15):
        raise ValueError(
            "Room width and length must be between 2 and 15 metres."
        )

    room_type = str(room_type).strip().lower()
    if room_type not in SUPPORTED_ROOMS:
        raise ValueError("Unsupported room type.")

    output_format = str(output_format).strip().lower()
    if output_format not in {"png", "pdf"}:
        raise ValueError("Output format must be png or pdf.")

    north_direction = str(north_direction).strip().lower()
    if north_direction not in VALID_DIRECTIONS:
        raise ValueError(
            "north_direction must be north, east, south, or west."
        )

    if placements is None:
        placements = []

    validated_placements = []

    for placement in placements:
        item = str(placement.get("item", "")).strip().lower()

        if not item:
            raise ValueError("Furniture item names cannot be empty.")

        if item not in FURNITURE_SIZES:
            raise ValueError(
                f"Unsupported furniture item '{item}'. "
                f"Supported items: {', '.join(FURNITURE_SIZES)}"
            )

        default_width, default_length = FURNITURE_SIZES[item]

        x = float(placement.get("x", 0.2))
        y = float(placement.get("y", 0.2))
        item_width = float(placement.get("width", default_width))
        item_length = float(placement.get("length", default_length))

        if item_width <= 0 or item_length <= 0:
            raise ValueError(
                f"Dimensions for '{item}' must be positive."
            )

        if (
            x < 0
            or y < 0
            or x + item_width > width
            or y + item_length > length
        ):
            raise ValueError(
                f"'{item}' extends outside the room boundary. "
                "Adjust its position or dimensions."
            )

        validated_placements.append({
            "item": item,
            "x": x,
            "y": y,
            "width": item_width,
            "length": item_length,
        })

    # Map the drawing edges to real-world directions.
    top_index = DIRECTION_ORDER.index(north_direction)

    top_direction = DIRECTION_ORDER[top_index]
    right_direction = DIRECTION_ORDER[(top_index + 1) % 4]
    bottom_direction = DIRECTION_ORDER[(top_index + 2) % 4]
    left_direction = DIRECTION_ORDER[(top_index + 3) % 4]

    fig, ax = plt.subplots(figsize=(8, 7))

    try:
        # Room boundary.
        ax.add_patch(
            Rectangle(
                (0, 0),
                width,
                length,
                fill=False,
                edgecolor="black",
                linewidth=3,
            )
        )

        # Draw furniture using the original coordinate system.
        for placement in validated_placements:
            item = placement["item"]
            x = placement["x"]
            y = placement["y"]
            item_width = placement["width"]
            item_length = placement["length"]

            ax.add_patch(
                Rectangle(
                    (x, y),
                    item_width,
                    item_length,
                    facecolor=FURNITURE_COLORS.get(
                        item, "lightgray"
                    ),
                    edgecolor="black",
                    linewidth=1.2,
                    alpha=0.85,
                )
            )

            ax.text(
                x + item_width / 2,
                y + item_length / 2,
                item.replace("_", " ").title(),
                ha="center",
                va="center",
                fontsize=8,
                wrap=True,
            )

        # Label each edge with its real-world direction.
        ax.text(
            width / 2,
            length + 0.12,
            top_direction.upper(),
            ha="center",
            va="bottom",
            fontsize=10,
        )

        ax.text(
            width / 2,
            -0.12,
            bottom_direction.upper(),
            ha="center",
            va="top",
            fontsize=10,
        )

        ax.text(
            -0.12,
            length / 2,
            left_direction.upper(),
            ha="right",
            va="center",
            rotation=90,
            fontsize=10,
        )

        ax.text(
            width + 0.12,
            length / 2,
            right_direction.upper(),
            ha="left",
            va="center",
            rotation=90,
            fontsize=10,
        )

        # Determine which edge represents north.
        if top_direction == "north":
            arrow_start = (width / 2, length + 0.75)
            arrow_end = (width / 2, length + 0.25)
            north_label_position = (
                width / 2, length + 0.83
            )
            north_label_alignment = "bottom"

        elif right_direction == "north":
            arrow_start = (width + 0.85, length / 2)
            arrow_end = (width + 0.25, length / 2)
            north_label_position = (
                width + 0.90, length / 2 + 0.12
            )
            north_label_alignment = "bottom"

        elif bottom_direction == "north":
            arrow_start = (width / 2, -0.75)
            arrow_end = (width / 2, -0.25)
            north_label_position = (
                width / 2, -0.83
            )
            north_label_alignment = "top"

        else:
            arrow_start = (-0.85, length / 2)
            arrow_end = (-0.25, length / 2)
            north_label_position = (
                -0.90, length / 2 + 0.12
            )
            north_label_alignment = "bottom"

        # North arrow points toward the edge labelled NORTH.
        ax.annotate(
            "",
            xy=arrow_end,
            xytext=arrow_start,
            arrowprops={
                "arrowstyle": "->",
                "linewidth": 2,
            },
        )

        ax.text(
            north_label_position[0],
            north_label_position[1],
            "NORTH",
            ha="center",
            va=north_label_alignment,
            fontsize=9,
            fontweight="bold",
        )

        # Room dimensions.
        ax.text(
            width / 2,
            -0.42,
            f"{width:.2f} m",
            ha="center",
            va="top",
            fontsize=10,
        )

        ax.text(
            -0.48,
            length / 2,
            f"{length:.2f} m",
            rotation=90,
            ha="right",
            va="center",
            fontsize=10,
        )

        ax.set_xlim(-1.1, width + 1.1)
        ax.set_ylim(-1.05, length + 1.0)
        ax.set_aspect("equal")
        ax.axis("off")

        ax.set_title(
            f"Preliminary {room_type.replace('_', ' ').title()} "
            "Floor Plan\n"
            f"Top of drawing: {top_direction.upper()} | "
            "Dimensions and furniture positions are user-supplied"
        )

        # Render the floor plan as PNG in memory.
        image_buffer = BytesIO()

        fig.savefig(
            image_buffer,
            format="png",
            dpi=180,
            bbox_inches="tight",
        )

        png_bytes = image_buffer.getvalue()

    finally:
        plt.close(fig)

    if output_format == "png":
        return png_bytes

    # Convert the rendered PNG to PDF.
    pdf_buffer = BytesIO()
    pdf = canvas.Canvas(pdf_buffer)
    pdf.setTitle("Preliminary Room Floor Plan")

    pdf.drawImage(
        ImageReader(BytesIO(png_bytes)),
        40,
        80,
        width=520,
        height=650,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )

    pdf.save()
    return pdf_buffer.getvalue()
