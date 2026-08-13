# HRDPA precipitation for GeoLibre

This project audits the GEE HRDPA daily archive from May 1 through an inclusive end date, reports gaps, downloads every available day at 2.5 km clipped to the Prairie ROI, and writes one CF-aware Zarr v2 cube with dimensions `(time, y, x)`. It also provides browser-ready COG time series for GeoLibre.

Configured sources:

- GEE collection: `projects/climate-engine-pro/assets/ce-hrdpa-daily`
- Prairie ROI: `projects/plan-hardiness/assets/SHP_others/Prairies_Provinces_intersected`
- Cloud Project: `plan-hardiness`
- Native output grid: EPSG:3978, 2,500 m
- Cube: `output/hrdpa_prairies_daily.zarr`, variable `precipitation`

## Setup

```powershell
conda env create -f environment.yml
conda activate geolibre-hrdpa
earthengine authenticate --force --auth_mode=localhost
```

Sign into Earth Engine as `ndacusask@gmail.com`. That identity must be registered for Earth Engine and have permission to use the `plan-hardiness` Cloud Project, including `serviceusage.services.use`, and read both assets.

## Run the GEE and GeoZarr pipeline

The defaults are May 1 of the current year through today, both inclusive:

```powershell
hrdpa-pipeline audit
hrdpa-pipeline run
```

For a fixed period:

```powershell
hrdpa-pipeline run --start 2026-05-01 --end 2026-08-13
```

Downloads are resumable. Existing daily TIFFs are skipped unless `--overwrite` is supplied. Missing GEE dates are reported but are not synthesized in the cube. Duplicate images for a date are flagged and mosaicked.

## Outputs for May 1-August 13, 2026

The audit found eight available dates (`2026-08-05` through `2026-08-12`) and 97 missing dates:

- `reports/date_audit.csv` and `reports/date_audit.json`: date availability reports
- `data/daily`: original clipped EPSG:3978 GeoTIFF downloads
- `output/hrdpa_prairies_daily.zarr`: eight-slice GeoZarr cube
- `data/cog_web`: EPSG:3857 browser-ready COGs with all valid values
- `data/cog_web_5mm`: COGs with precipitation below 5 mm transparent
- `data/cog_web_10mm`: COGs with precipitation below 10 mm transparent

## GeoLibre Time Slider

The installed GeoLibre build displays the Zarr cube but does not expose the layer-menu action needed to bind its internal `time` dimension to the Time Slider. Use the dated COG series for animation.

### GitHub Pages publication

The `docs/` directory is a self-contained public site containing the timelapse viewer and eight 10 mm-threshold COGs. The workflow `.github/workflows/pages.yml` deploys it automatically from the `main` branch. After publishing a repository named `REPOSITORY`, the viewer URL is:

```text
https://USERNAME.github.io/REPOSITORY/
```

The COG template for GeoLibre is:

```text
https://USERNAME.github.io/REPOSITORY/data/cog_web_10mm/hrdpa_{date:YYYY-MM-DD}.tif
```

### 1. Start the range-enabled COG server

From the repository root:

```powershell
python scripts/serve_cogs.py
```

Keep the terminal open while using GeoLibre. This server supplies CORS headers and HTTP `206 Partial Content` byte-range responses required by browser COG readers. Do not use `python -m http.server` for the COG workflow.

### 2. Add the animated layer

Open **Time Slider -> Add a data source**, choose **COG**, and use the 10 mm transparency series:

```text
http://127.0.0.1:8000/data/cog_web_10mm/hrdpa_{date:YYYY-MM-DD}.tif
```

Configure:

- Name: `Daily precipitation`
- Engine: browser-local GPU/WASM engine when available
- Colormap: custom blue ramp shown below
- Rescale: `10` to `70`
- NoData: `-9999`
- Bands: `1` (not `1,2,3`)
- Granularity: `Day`
- Start date: `2026-08-05`
- End date: `2026-08-12`
- Initial date: `2026-08-05`
- Date format: `YYYY-MM-DD`
- Interval: `1`
- Speed: `800` ms/step
- Loop playback: enabled

To make only values below 5 mm transparent, use:

```text
http://127.0.0.1:8000/data/cog_web_5mm/hrdpa_{date:YYYY-MM-DD}.tif
```

For that series, use a rescale range of `5` to `70`.

### 3. Colorbar

Use the same continuous blue ramp for the layer and colorbar:

```text
#f7fbff, #c6dbef, #6baed6, #2171b5, #08306b
```

For the 10 mm product, associate the stops approximately with `10, 25, 40, 55, 70 mm`. Use the title `Daily precipitation (mm)`. In GeoLibre, enable **View -> Colorbar** when that control is available.

### Hosted GeoLibre limitation

The remote TiTiler endpoint cannot read files from `127.0.0.1` on this computer. When using `https://web.geolibre.app`, select a browser-local engine that reads COGs directly. Otherwise, publish the COGs at a public HTTPS URL or use the GeoLibre desktop app.

A request such as the following fails because `127.0.0.1` refers to the remote TiTiler machine, not this workstation:

```text
https://titiler.d2s.org/cog/info?url=http://127.0.0.1:8000/...
```

## Create another transparency threshold

The original `data/cog_web` files remain unchanged. Generate a derived COG series with a different threshold using the working `geedim` environment:

```powershell
conda run -n geedim python scripts\mask_cogs.py --threshold 10 --output data\cog_web_10mm
```

All values below the threshold are replaced by NoData (`-9999`) and render transparently. The `geolibre-hrdpa` environment may show a Rasterio/GDAL DLL mismatch on this machine; use `geedim` for this utility.

## Open the GeoZarr cube directly

For analysis or manual time selection, open **Add Data -> Zarr Layer**, choose `output/hrdpa_prairies_daily.zarr`, and select variable `precipitation`.

- Dimensions: `(time, y, x)`
- CRS: `EPSG:3978`
- Raw time values: `20670` through `20677`
- Corresponding dates: August 5-12, 2026

For example:

```json
{"time": 20670}
```

## Validate

```powershell
pytest -q
python -c "import xarray as xr; print(xr.open_zarr('output/hrdpa_prairies_daily.zarr', consolidated=True))"
conda run -n geedim rio cogeo validate data\cog_web_10mm\hrdpa_2026-08-10.tif
```
