from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

COLLECTION = "projects/climate-engine-pro/assets/ce-hrdpa-daily"
ROI = "projects/plan-hardiness/assets/SHP_others/Prairies_Provinces_intersected"
PROJECT = "plan-hardiness"
CRS = "EPSG:3978"
SCALE_METRES = 2500
DATE_RE = re.compile(r"hrdpa_(\d{4}-\d{2}-\d{2})\.tif$")


@dataclass(frozen=True)
class Audit:
    start: str
    end: str
    collection: str
    expected_count: int
    available_dates: list[str]
    missing_dates: list[str]
    duplicate_dates: list[str]
    image_count: int
    band_names: list[str]
    generated_at_utc: str


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def date_range(start: date, end: date) -> list[date]:
    """Return inclusive calendar dates."""
    if end < start:
        raise ValueError("end date must be on or after start date")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def default_start(today: date | None = None) -> date:
    today = today or date.today()
    return date(today.year, 5, 1)


def initialize_ee(project: str = PROJECT):
    import ee

    try:
        ee.Initialize(project=project)
    except Exception as exc:
        message = str(exc)
        if "USER_PROJECT_DENIED" in message or "serviceusage.services.use" in message:
            raise RuntimeError(
                f"The cached Earth Engine account cannot use Cloud Project {project!r}. "
                "Run `earthengine authenticate --force --auth_mode=localhost` and sign in as "
                "ndacusask@gmail.com, then ensure that account has Service Usage Consumer and "
                "Earth Engine access on the project."
            ) from exc
        raise RuntimeError(
            "Earth Engine initialization failed. Run `earthengine authenticate "
            "--auth_mode=localhost` and retry."
        ) from exc
    return ee


def audit_collection(start: date, end: date, collection: str = COLLECTION, project: str = PROJECT) -> Audit:
    ee = initialize_ee(project)
    # filterDate has an exclusive end, hence the extra day.
    images = ee.ImageCollection(collection).filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
    millis = images.aggregate_array("system:time_start").getInfo()
    dates = [datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat() for ms in millis]
    counts: dict[str, int] = {}
    for item in dates:
        counts[item] = counts.get(item, 0) + 1
    expected = [d.isoformat() for d in date_range(start, end)]
    available = sorted(counts)
    return Audit(
        start=start.isoformat(),
        end=end.isoformat(),
        collection=collection,
        expected_count=len(expected),
        available_dates=available,
        missing_dates=sorted(set(expected) - set(available)),
        duplicate_dates=sorted(k for k, v in counts.items() if v > 1),
        image_count=len(dates),
        band_names=ee.Image(images.first()).bandNames().getInfo() if dates else [],
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def write_audit(audit: Audit, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "date_audit.json").write_text(json.dumps(asdict(audit), indent=2) + "\n", encoding="utf-8")
    available = set(audit.available_dates)
    duplicates = set(audit.duplicate_dates)
    with (report_dir / "date_audit.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["date", "status"])
        for day in date_range(parse_date(audit.start), parse_date(audit.end)):
            key = day.isoformat()
            writer.writerow([key, "duplicate" if key in duplicates else "available" if key in available else "missing"])


def choose_band(bands: list[str], requested: str | None) -> str:
    if requested:
        if requested not in bands:
            raise ValueError(f"Band {requested!r} is not present; collection bands: {bands}")
        return requested
    if len(bands) != 1:
        raise ValueError(f"Collection has {len(bands)} bands {bands}; pass --band explicitly")
    return bands[0]


def download_available(
    audit: Audit,
    destination: Path,
    band: str | None = None,
    collection: str = COLLECTION,
    roi_asset: str = ROI,
    project: str = PROJECT,
    crs: str = CRS,
    scale: int = SCALE_METRES,
    overwrite: bool = False,
) -> str:
    from geedim.download import BaseImage

    ee = initialize_ee(project)
    selected_band = choose_band(audit.band_names, band)
    roi = ee.FeatureCollection(roi_asset).geometry()
    destination.mkdir(parents=True, exist_ok=True)
    for day_text in audit.available_dates:
        target = destination / f"hrdpa_{day_text}.tif"
        if target.exists() and not overwrite:
            continue
        day = parse_date(day_text)
        daily = (
            ee.ImageCollection(collection)
            .filterDate(day.isoformat(), (day + timedelta(days=1)).isoformat())
            .select(selected_band)
            .mosaic()
            .rename("precipitation")
            .clip(roi)
            .set({"system:time_start": ee.Date(day.isoformat()).millis(), "source_band": selected_band})
        )
        BaseImage(daily).download(
            target,
            overwrite=overwrite,
            region=roi,
            crs=crs,
            scale=scale,
            dtype="float32",
        )
    return selected_band


def tif_date(path: Path) -> date:
    match = DATE_RE.search(path.name)
    if not match:
        raise ValueError(f"Unexpected daily raster name: {path.name}")
    return parse_date(match.group(1))


def build_cube(daily_dir: Path, output: Path, audit: Audit | None = None) -> int:
    import numpy as np
    import rasterio
    import xarray as xr
    from numcodecs import Blosc

    paths = sorted(daily_dir.glob("hrdpa_????-??-??.tif"), key=tif_date)
    if not paths:
        raise FileNotFoundError(f"No daily HRDPA GeoTIFFs found in {daily_dir}")

    arrays = []
    reference = None
    for path in paths:
        with rasterio.open(path) as src:
            signature = (src.crs.to_string(), src.transform, src.width, src.height)
            if reference is None:
                reference = signature
                transform, crs_wkt = src.transform, src.crs.to_wkt()
                x = transform.c + (np.arange(src.width) + 0.5) * transform.a
                y = transform.f + (np.arange(src.height) + 0.5) * transform.e
            elif signature != reference:
                raise ValueError(f"Raster grid mismatch: {path} differs from the first daily raster")
            data = src.read(1).astype("float32")
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            arrays.append(data)

    times = np.array([np.datetime64(tif_date(p), "ns") for p in paths])
    cube = np.stack(arrays, axis=0)
    ds = xr.Dataset(
        data_vars={
            "precipitation": (
                ("time", "y", "x"),
                cube,
                {
                    "long_name": "Daily HRDPA precipitation",
                    "standard_name": "lwe_thickness_of_precipitation_amount",
                    "units": "mm",
                    "grid_mapping": "spatial_ref",
                },
            ),
            "spatial_ref": ((), 0, {"spatial_ref": crs_wkt, "crs_wkt": crs_wkt, "GeoTransform": " ".join(map(str, transform.to_gdal()))}),
        },
        coords={"time": times, "y": y, "x": x},
        attrs={
            "title": "HRDPA daily precipitation over the Canadian Prairies",
            "source": COLLECTION,
            "roi": ROI,
            "Conventions": "CF-1.10",
            "history": f"Created {datetime.now(timezone.utc).isoformat()}",
        },
    )
    ds.x.attrs.update({"axis": "X", "standard_name": "projection_x_coordinate", "units": "m"})
    ds.y.attrs.update({"axis": "Y", "standard_name": "projection_y_coordinate", "units": "m"})
    ds.time.attrs.update({"axis": "T", "standard_name": "time"})
    chunks = (1, min(256, cube.shape[1]), min(256, cube.shape[2]))
    encoding = {
        "precipitation": {"dtype": "float32", "chunks": chunks, "compressor": Blosc(cname="zstd", clevel=5, shuffle=Blosc.BITSHUFFLE), "_FillValue": -9999.0},
        "time": {"dtype": "int32", "units": "days since 1970-01-01 00:00:00", "calendar": "proleptic_gregorian"},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    ds.to_zarr(output, mode="w", consolidated=True, encoding=encoding, zarr_version=2)

    if audit:
        downloaded = {tif_date(p).isoformat() for p in paths}
        missing_downloads = sorted(set(audit.available_dates) - downloaded)
        if missing_downloads:
            raise RuntimeError(f"Cube was written but available GEE dates were not downloaded: {missing_downloads}")
    return len(paths)
