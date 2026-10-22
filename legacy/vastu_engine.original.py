
# --------------------------------------------------
# VASTU AI ENGINE
# Orientation-aware room-side analysis
# --------------------------------------------------

DIRECTIONAL_RULES = {
    "bedroom": {
        "bed": {
            "preferred": ["south", "east"],
            "avoid": ["north"],
            "reason": (
                "Traditional Vastu guidance commonly prefers "
                "the head toward the south or east while sleeping."
            ),
        },
        "wardrobe": {
            "preferred": ["south", "west"],
            "avoid": [],
            "reason": (
                "Heavy storage is traditionally suggested along "
                "the south or west side."
            ),
        },
    },
    "living_room": {
        "seating": {
            "preferred": ["south", "west"],
            "avoid": [],
            "reason": (
                "Traditional layouts often place heavier seating "
                "toward the south or west."
            ),
        },
    },
    "kitchen": {
        "stove": {
            "preferred": ["east"],
            "avoid": [],
            "reason": (
                "Traditional Vastu guidance commonly prefers "
                "cooking while facing east."
            ),
        },
    },
}

VALID_DIRECTIONS = {"north", "south", "east", "west"}

# Clockwise compass order.
CARDINAL_DIRECTIONS = ["north", "east", "south", "west"]


# --------------------------------------------------
# BASIC DIRECTIONAL VASTU ANALYSIS
# --------------------------------------------------

def analyze_vastu(room_type: str, placements: dict) -> dict:
    """
    Compare supplied furniture directions with configured rules.

    Example:
        {"bed": "south", "wardrobe": "west"}

    The supplied direction is treated as an explicit direction,
    not inferred furniture facing or headboard orientation.
    """

    if room_type not in DIRECTIONAL_RULES:
        raise ValueError(
            "room_type must be bedroom, living_room, or kitchen."
        )

    results = []

    for item, direction in placements.items():
        item = str(item).lower().strip()
        direction = str(direction).lower().strip()

        if not item:
            raise ValueError("Furniture item names cannot be empty.")

        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"Invalid direction '{direction}' for '{item}'. "
                "Use north, south, east, or west."
            )

        rule = DIRECTIONAL_RULES[room_type].get(item)

        if rule is None:
            results.append({
                "item": item,
                "direction": direction,
                "status": "no_rule_defined",
                "recommendation": (
                    "No configured rule exists for this item."
                ),
            })
            continue

        if direction in rule["preferred"]:
            status = "preferred"
            recommendation = (
                "This placement matches the configured preference."
            )
        elif direction in rule["avoid"]:
            status = "review"
            recommendation = (
                "Consider another direction if practical and "
                "consistent with your room constraints."
            )
        else:
            status = "alternative"
            recommendation = (
                "This direction is not listed as preferred "
                "in the current rule set."
            )

        results.append({
            "item": item,
            "direction": direction,
            "status": status,
            "preferred_directions": rule["preferred"],
            "avoid_directions": rule["avoid"],
            "reason": rule["reason"],
            "recommendation": recommendation,
        })

    return {
        "room_type": room_type,
        "basis": "Configurable traditional Vastu guidance",
        "results": results,
        "disclaimer": (
            "These are traditional design preferences, not scientifically "
            "established requirements. Recommendations must respect "
            "safety, accessibility, and actual room constraints."
        ),
    }


# --------------------------------------------------
# ORIENTATION UTILITIES
# --------------------------------------------------

def rotate_direction(direction: str, quarter_turns: int) -> str:
    """
    Rotate a cardinal direction clockwise by a number of quarter turns.

    Examples:
        north + 1 -> east
        north + 2 -> south
        west + 1 -> north
    """

    direction = direction.lower().strip()

    if direction not in VALID_DIRECTIONS:
        raise ValueError(
            "Direction must be north, south, east, or west."
        )

    index = CARDINAL_DIRECTIONS.index(direction)
    return CARDINAL_DIRECTIONS[(index + quarter_turns) % 4]


def get_world_directions(north_direction: str) -> dict:
    """
    Map the local floor-plan axes to real-world cardinal directions.

    Coordinate convention:
        x increases to the right on the floor plan.
        y increases toward the top of the floor plan.

    north_direction describes the real-world direction represented
    by the TOP (+y) edge of the floor plan.

    Example:
        north_direction='east'
        top edge    -> east
        right edge  -> south
        bottom edge -> west
        left edge   -> north
    """

    north_direction = north_direction.lower().strip()

    if north_direction not in VALID_DIRECTIONS:
        raise ValueError(
            "north_direction must be north, south, east, or west."
        )

    top = north_direction
    right = rotate_direction(top, 1)
    bottom = rotate_direction(top, 2)
    left = rotate_direction(top, 3)

    return {
        "top": top,
        "right": right,
        "bottom": bottom,
        "left": left,
    }


# --------------------------------------------------
# ORIENTATION-AWARE COORDINATE ANALYSIS
# --------------------------------------------------

def analyze_vastu_coordinates(
    room_type: str,
    placements: list[dict],
    room_width: float,
    room_length: float,
    north_direction: str = "north",
) -> dict:
    """
    Estimate each furniture item's room-side position and evaluate
    it against the configured directional Vastu preferences.

    Parameters:
        room_type:
            bedroom, living_room, or kitchen

        placements:
            List of furniture objects with item, x, y, width, length.

        room_width:
            Width of the room in metres.

        room_length:
            Length of the room in metres.

        north_direction:
            Real-world direction represented by the top edge (+y)
            of the floor-plan coordinate system.

    Important:
        This estimates which room side contains a furniture item's
        center. It does not determine which way the object faces,
        nor does it infer a bed's headboard direction.
    """

    if room_type not in DIRECTIONAL_RULES:
        raise ValueError(
            "room_type must be bedroom, living_room, or kitchen."
        )

    if room_width <= 0 or room_length <= 0:
        raise ValueError("Room dimensions must be positive.")

    if not placements:
        raise ValueError(
            "At least one furniture placement is required."
        )

    world_directions = get_world_directions(north_direction)

    results = []

    for placement in placements:
        item = str(placement.get("item", "")).lower().strip()

        if not item:
            raise ValueError("Furniture item names cannot be empty.")

        try:
            x = float(placement["x"])
            y = float(placement["y"])
            item_width = float(placement["width"])
            item_length = float(placement["length"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Placement for '{item}' must include numeric "
                "x, y, width, and length."
            ) from exc

        if item_width <= 0 or item_length <= 0:
            raise ValueError(
                f"Dimensions for '{item}' must be positive."
            )

        if (
            x < 0
            or y < 0
            or x + item_width > room_width
            or y + item_length > room_length
        ):
            raise ValueError(
                f"'{item}' extends outside the room boundary."
            )

        center_x = x + item_width / 2
        center_y = y + item_length / 2

        # Identify the local quadrant containing the furniture center.
        local_horizontal_side = (
            "left"
            if center_x < room_width / 2
            else "right"
        )

        local_vertical_side = (
            "bottom"
            if center_y < room_length / 2
            else "top"
        )

        # Convert local floor-plan sides into real-world directions.
        horizontal_direction = world_directions[
            local_horizontal_side
        ]
        vertical_direction = world_directions[
            local_vertical_side
        ]

        room_side = [
            vertical_direction,
            horizontal_direction,
        ]

        # Determine the dominant offset from the room center.
        # This selects a preliminary side for rule evaluation.
        horizontal_offset = abs(center_x - room_width / 2)
        vertical_offset = abs(center_y - room_length / 2)

        if horizontal_offset >= vertical_offset:
            evaluated_direction = horizontal_direction
        else:
            evaluated_direction = vertical_direction

        rule = DIRECTIONAL_RULES[room_type].get(item)

        result = {
            "item": item,
            "center_coordinates_metres": {
                "x": round(center_x, 3),
                "y": round(center_y, 3),
            },
            "local_room_sides": [
                local_vertical_side,
                local_horizontal_side,
            ],
            "room_side": room_side,
            "evaluated_direction": evaluated_direction,
        }

        if rule is None:
            result.update({
                "status": "no_rule_defined",
                "recommendation": (
                    "No configured rule exists for this item."
                ),
            })
            results.append(result)
            continue

        if evaluated_direction in rule["preferred"]:
            status = "preferred"
            recommendation = (
                "The estimated room-side position matches a "
                "configured traditional preference."
            )
        elif evaluated_direction in rule["avoid"]:
            status = "review"
            recommendation = (
                "Consider an alternative placement if practical "
                "and consistent with room constraints."
            )
        else:
            status = "alternative"
            recommendation = (
                "The estimated room-side position is not listed "
                "as preferred in the current rule set."
            )

        result.update({
            "status": status,
            "preferred_directions": rule["preferred"],
            "avoid_directions": rule["avoid"],
            "reason": rule["reason"],
            "recommendation": recommendation,
        })

        results.append(result)

    return {
        "room_type": room_type,
        "room_dimensions_metres": {
            "width": room_width,
            "length": room_length,
        },
        "north_direction": north_direction,
        "coordinate_orientation": world_directions,
        "basis": (
            "Orientation-aware, coordinate-derived preliminary "
            "room-side assessment"
        ),
        "results": results,
        "limitations": [
            "Furniture positions are supplied by the user.",
            "Room-side positions are estimated from furniture centers.",
            "This does not determine furniture facing direction.",
            "Bed headboard orientation is not inferred.",
            "The floor-plan image itself is not rotated by this function.",
        ],
        "disclaimer": (
            "These are configurable traditional design preferences, "
            "not scientifically established requirements. The estimated "
            "side is not a complete Vastu assessment."
        ),
    }
