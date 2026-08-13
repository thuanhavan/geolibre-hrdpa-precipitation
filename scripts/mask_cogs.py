"""Create COG copies with precipitation below a threshold set to NoData."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles


def mask_cog(source: Path, destination: Path, threshold: float, nodata: float) -> None:
    with rasterio.open(source) as src:
        data = src.read(1).astype("float32")
        data[(~np.isfinite(data)) | (data < threshold)] = nodata
        profile = src.profile.copy()
        profile.update(driver="GTiff", dtype="float32", count=1, nodata=nodata)

        with tempfile.TemporaryDirectory() as temp_dir:
            temporary = Path(temp_dir) / source.name
            with rasterio.open(temporary, "w", **profile) as dst:
                dst.write(data, 1)
                dst.update_tags(**src.tags())
                dst.update_tags(1, **src.tags(1))

            destination.parent.mkdir(parents=True, exist_ok=True)
            cog_profile = cog_profiles.get("deflate")
            cog_profile.update({"blockxsize": 256, "blockysize": 256})
            cog_translate(
                temporary,
                destination,
                cog_profile,
                nodata=nodata,
                overview_resampling="average",
                in_memory=True,
                quiet=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/cog_web"))
    parser.add_argument("--output", type=Path, default=Path("data/cog_web_5mm"))
    parser.add_argument("--threshold", type=float, default=5.0)
    parser.add_argument("--nodata", type=float, default=-9999.0)
    args = parser.parse_args()

    sources = sorted(args.input.glob("hrdpa_????-??-??.tif"))
    if not sources:
        raise SystemExit(f"No HRDPA COGs found in {args.input}")
    for source in sources:
        target = args.output / source.name
        mask_cog(source, target, args.threshold, args.nodata)
        print(f"Wrote {target}")


if __name__ == "__main__":
    main()
