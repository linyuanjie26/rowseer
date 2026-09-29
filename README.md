# RowSeer

A polished starter app to log practices, compare training volume, and spot pacing trends across water sessions, ergs, and races. It is a compact data project that turns everyday training into a resume-ready analytics dashboard.

## v1 features

- Load realistic sample practices or upload a CSV with the same schema.
- Add practices from a sidebar form without modifying the source file.
- Review a clean practice table with computed `/500m` pace.
- Track weekly meters and pace over time with interactive Plotly charts.
- See season totals, practice count, and fastest pace on pieces of at least 1,000m.
- Download the updated in-memory log as a CSV.

## Run locally

```bash
cd ~/Downloads/rowseer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens in a browser at the local Streamlit URL.

## Tech stack

- **Python** for data processing and app logic
- **Streamlit** for the interactive dashboard
- **pandas** for tabular cleaning and aggregation
- **Plotly** for responsive charts

## What's next

- Import activities from Strava or Garmin.
- Export polished weekly or season summaries to PDF.
- Add split-by-split intervals, RPE, heart rate, boat class, and crew context.

## Data schema

CSV files should contain `date`, `type`, `distance_m`, `time_sec`, and `notes`. Dates use `YYYY-MM-DD`; `type` is `water`, `erg`, or `race`.
