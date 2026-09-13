# Adyatithi

A Hugo site presenting Hindu festivals, vratas and observances — shlokas,
descriptions, names across languages, and timing — browsable by month,
devatā, tithi, nakṣatra and tag.

Live at https://adyatithi.github.io/

## Data source

Content is generated from the [adyatithi](https://github.com/jyotisham/adyatithi)
TOML festival archive via `scripts/build_content.py`, which parses the
source files and derives the site's taxonomies (month/tithi/nakshatra/devata)
from each entry's timing metadata and folder location.

The site currently ships a curated subset of the ~1700 available entries.
To regenerate `content/festivals/`:

```sh
python3 scripts/build_content.py --data-dir /path/to/adyatithi --limit 110
# or, for the full dataset:
python3 scripts/build_content.py --data-dir /path/to/adyatithi --all
```

Commit the resulting changes under `content/festivals/` — the GitHub Actions
workflow just builds whatever is committed, it does not re-run the pipeline.

## Local development

```sh
hugo server -D
```
