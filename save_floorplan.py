
import base64
import json
from pathlib import Path

# Paste the complete API response JSON into response.json
response_path = Path("response.json")

with response_path.open("r", encoding="utf-8") as file:
    data = json.load(file)

image_data = data["floorplan_png_base64"]
image_bytes = base64.b64decode(image_data)

output_path = Path("floorplan_preview.png")
output_path.write_bytes(image_bytes)

print(f"Floor plan saved to: {output_path.resolve()}")
print(f"Image size: {len(image_bytes):,} bytes")
