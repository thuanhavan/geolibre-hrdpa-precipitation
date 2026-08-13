"""Replace a GeoLibre HTML export's embedded project with a saved project JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROJECT_RE = re.compile(
    r'(<script type="application/json" id="geolibre-project">)(.*?)(</script>)',
    re.DOTALL,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path, help="GeoLibre standalone HTML export")
    parser.add_argument("project", type=Path, help="working .geolibre.json project")
    parser.add_argument("--output", type=Path, help="output HTML (default: <name>-fixed.html)")
    parser.add_argument(
        "--normalize-hrdpa",
        action="store_true",
        help="replace duplicate Time Slider sources with the known HRDPA COG source",
    )
    args = parser.parse_args()

    document = args.html.read_text(encoding="utf-8")
    project = json.loads(args.project.read_text(encoding="utf-8"))
    slider = project.get("plugins", {}).get("settings", {}).get("maplibre-gl-time-slider")
    if not slider or not slider.get("sources"):
        raise SystemExit("Saved project has no Time Slider sources; refusing to patch HTML")
    if args.normalize_hrdpa:
        existing = slider["sources"][-1]
        slider["sources"] = [
            {
                "type": "cog",
                "id": existing.get("id", "hrdpa-precipitation"),
                "name": "HRDPA Precipitation",
                "url": "http://127.0.0.1:8000/data/cog_web_10mm/hrdpa_{date:YYYY-MM-DD}.tif",
                "engine": "wasm",
                "colormap": "blues",
                "rescale": [10, 70],
                "nodata": -9999,
                "bidx": [1],
                "opacity": 1,
                "visible": True,
            }
        ]
        slider.update(
            {
                "startDate": "2026-08-05T00:00:00.000Z",
                "endDate": "2026-08-12T00:00:00.000Z",
                "currentDate": "2026-08-08T00:00:00.000Z",
                "interval": 1,
                "granularity": "day",
                "granularities": ["day"],
            }
        )

    # Escape '<' so project strings cannot prematurely terminate the script tag.
    payload = json.dumps(project, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    replacement = lambda match: match.group(1) + payload + match.group(3)
    patched, count = PROJECT_RE.subn(replacement, document, count=1)
    if count != 1:
        raise SystemExit("Could not find exactly one embedded GeoLibre project in the HTML")

    output = args.output or args.html.with_name(f"{args.html.stem}-fixed.html")
    output.write_text(patched, encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
