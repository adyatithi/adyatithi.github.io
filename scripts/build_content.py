#!/usr/bin/env python3
"""Build Hugo content pages from adyatithi TOML festival data.

Walks a curated set of top-level directories in the adyatithi data repo,
parses each festival TOML file, derives human-readable taxonomy values
(month / tithi / nakshatra / devata / category) from the timing metadata
and folder structure, and emits one Hugo content file per festival under
content/festivals/.

Usage:
    python3 scripts/build_content.py [--data-dir PATH] [--limit N] [--all]
"""
import argparse
import re
import sys
import tomllib
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = Path(
    "/home/karthik/GitHub/jyotisha/jyotisha/panchaanga/temporal/festival/data"
)

# Only these top-level dirs are treated as "festival" content for the site.
# mahApuruSha (biographies / historical events, incl. some grim modern
# history entries) is deliberately excluded from the festival showcase.
INCLUDED_ROOTS = [
    "general",
    "devatA",
    "tamil",
    "temples",
    "gRhya",
    "time_focus",
]

CATEGORY_META = {
    "general": ("General Observances", "Pan-Hindu vratas, festivals and special days."),
    "devatA": ("Devatā Observances", "Festivals organized by the presiding deity."),
    "tamil": ("Tamil Traditions", "Festivals and observances from Tamil tradition."),
    "temples": ("Temple Festivals", "Festivals tied to specific temples and regions."),
    "gRhya": ("Gṛhya Rites", "Household-rite (gṛhyasūtra) observances."),
    "time_focus": ("Calendrical Specials", "Observances defined by rare or recurring time-patterns."),
}

DEVATA_META = {
    "shaiva": "Śaiva",
    "vaiShNava": "Vaiṣṇava",
    "shakti": "Śākta",
    "kaumAra": "Kaumāra (Skanda/Murugan)",
    "gaNapati": "Gāṇapatya (Gaṇeśa)",
    "lakShmI": "Lakṣmī",
    "umA": "Umā",
    "devIparva": "Devī Parva",
    "dashamahAvidyA": "Daśamahāvidyā",
    "graha": "Graha (Planetary)",
    "nadI": "Nadī (River)",
    "pitR": "Pitṛ (Ancestral)",
    "misc-fauna": "Fauna",
    "misc-flora": "Flora",
}

MONTHS = {
    1: ("Caitra", "चैत्र"), 2: ("Vaiśākha", "वैशाख"), 3: ("Jyeṣṭha", "ज्येष्ठ"),
    4: ("Āṣāḍha", "आषाढ"), 5: ("Śrāvaṇa", "श्रावण"), 6: ("Bhādrapada", "भाद्रपद"),
    7: ("Āśvina", "आश्विन"), 8: ("Kārtika", "कार्तिक"), 9: ("Mārgaśira", "मार्गशिर"),
    10: ("Pauṣa", "पौष"), 11: ("Māgha", "माघ"), 12: ("Phālguna", "फाल्गुन"),
}

TITHI_SHUKLA = [
    "Pratipat", "Dvitīyā", "Tṛtīyā", "Caturthī", "Pañcamī", "Ṣaṣṭhī", "Saptamī",
    "Aṣṭamī", "Navamī", "Daśamī", "Ekādaśī", "Dvādaśī", "Trayodaśī", "Caturdaśī",
    "Pūrṇimā",
]
TITHI_KRISHNA = [
    "Pratipat", "Dvitīyā", "Tṛtīyā", "Caturthī", "Pañcamī", "Ṣaṣṭhī", "Saptamī",
    "Aṣṭamī", "Navamī", "Daśamī", "Ekādaśī", "Dvādaśī", "Trayodaśī", "Caturdaśī",
    "Amāvāsyā",
]

NAKSHATRAS = [
    "Aśvinī", "Bharaṇī", "Kṛttikā", "Rohiṇī", "Mṛgaśira", "Ārdrā", "Punarvasu",
    "Puṣya", "Āśleṣā", "Maghā", "Pūrva Phalgunī", "Uttara Phalgunī", "Hasta",
    "Citrā", "Svātī", "Viśākhā", "Anurādhā", "Jyeṣṭhā", "Mūla", "Pūrva Āṣāḍha",
    "Uttara Āṣāḍha", "Śravaṇa", "Dhaniṣṭhā", "Śatabhiṣā", "Pūrva Bhādrapadā",
    "Uttara Bhādrapadā", "Revatī",
]

# ids we always want represented in the curated subset, if found.
PRIORITY_IDS = {
    "dIpAvalI_or_lakSmI-kubEra-pUjA", "mahAzivarAtriH", "zarannavarAtra-ArambhaH",
    "vasantanavarAtra-ArambhaH", "kRSNajanmASTamI-smArta", "kRSNajanmASTamI",
    "vinAyakacaturthI", "rAmanavamI", "rakSAbandhanam", "makara-saGkrAntiH",
    "holikA-pUrNamAsI", "ugAdi", "ratha-saptamI", "kArtIkI-EkAdazI",
    "vaikuNTha-EkAdazI", "guru-pUrNimA", "nAgapaJcamI", "gaGgA-daSaharA",
    "onam", "pongal",
}


def tithi_name(n: int) -> tuple[str, str]:
    """Return (tithi name, paksha) for a 1-30 anga_number."""
    if 1 <= n <= 15:
        return TITHI_SHUKLA[n - 1], "Śukla Pakṣa"
    idx = n - 16
    if 0 <= idx < 15:
        return TITHI_KRISHNA[idx], "Kṛṣṇa Pakṣa"
    return f"Tithi {n}", ""


def nakshatra_name(n: int) -> str:
    if 1 <= len(NAKSHATRAS) and 1 <= n <= len(NAKSHATRAS):
        return NAKSHATRAS[n - 1]
    return f"Nakṣatra {n}"


def toml_str(s: str) -> str:
    """A safe single-line TOML basic string."""
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{s}"'


def toml_multiline(s: str) -> str:
    """A safe TOML literal multi-line string."""
    s = s.strip("\n")
    s = s.replace("'''", "' ' '")
    return f"'''\n{s}\n'''"


def toml_list(items) -> str:
    return "[" + ", ".join(toml_str(str(i)) for i in items) + "]"


def slugify(raw_id: str) -> str:
    s = raw_id.replace("★", "").strip()
    s = re.sub(r"[~_/]+", "-", s)
    s = re.sub(r"[^A-Za-z0-9\-]+", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s.lower() or "festival"


GENERIC_ID_PATTERN = re.compile(
    r"(mAsaH$|-?ArambhaH$|sAmAnyaniyamAH|-mAsa-ArambhaH)"
)


def score(record: dict) -> float:
    s = 0.0
    if record.get("shlokas"):
        s += 5
    if record.get("description_en"):
        s += 3
    s += 0.5 * len(record.get("names", {}))
    s += 0.25 * len(record.get("tags", []))
    if record["id"] in PRIORITY_IDS:
        s += 100
    if "RareDays" in record.get("tags", []):
        s -= 1
    if GENERIC_ID_PATTERN.search(record["id"]) and not record.get("shlokas"):
        s -= 6
    return s


def parse_file(path: Path, data_dir: Path) -> dict | None:
    try:
        with path.open("rb") as f:
            doc = tomllib.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"  ! failed to parse {path}: {e}", file=sys.stderr)
        return None

    fid = doc.get("id") or path.stem
    rel = path.relative_to(data_dir)
    parts = rel.parts
    root = parts[0]

    record: dict = {
        "id": fid,
        "source_path": str(rel),
        "tags": doc.get("tags", []),
        "shlokas": (doc.get("shlokas") or "").strip(),
        "description_en": ((doc.get("description") or {}).get("en") or "").strip(),
        "names": {k: v for k, v in (doc.get("names") or {}).items() if v},
        "references": doc.get("references_secondary", []),
    }

    timing = doc.get("timing") or {}
    month_num = timing.get("month_number")
    anga_type = timing.get("anga_type")
    anga_number = timing.get("anga_number")

    record["month"] = []
    record["tithi"] = []
    record["nakshatra"] = []
    record["timing_summary_parts"] = []

    if isinstance(month_num, int) and month_num in MONTHS:
        iast, deva = MONTHS[month_num]
        record["month"] = [iast]
        record["timing_summary_parts"].append(f"{iast} ({deva}) māsa")

    if anga_type == "tithi" and isinstance(anga_number, int):
        name, paksha = tithi_name(anga_number)
        record["tithi"] = [name]
        record["timing_summary_parts"].append(f"{paksha} {name}")
    elif anga_type == "nakshatra" and isinstance(anga_number, int):
        name = nakshatra_name(anga_number)
        record["nakshatra"] = [name]
        record["timing_summary_parts"].append(f"{name} nakṣatra")

    if timing.get("kaala"):
        record["kaala"] = timing["kaala"]
        record["timing_summary_parts"].append(f"at {timing['kaala']}")
    if timing.get("priority"):
        record["priority"] = timing["priority"]
    if timing.get("month_type") == "gregorian":
        record["timing_summary_parts"] = [
            f"{timing.get('month_number')}/{timing.get('anga_number')} (Gregorian)"
        ]

    # devata: immediate child folder under devatA/
    record["devata"] = []
    if root == "devatA" and len(parts) > 2:
        key = parts[1]
        record["devata"] = [DEVATA_META.get(key, key)]

    cat_name, _ = CATEGORY_META.get(root, (root, ""))
    record["category"] = [cat_name]
    record["category_root"] = root

    return record


def build(data_dir: Path, limit: int | None):
    candidates = []
    for root in INCLUDED_ROOTS:
        root_dir = data_dir / root
        if not root_dir.exists():
            continue
        for path in sorted(root_dir.rglob("*.toml")):
            rec = parse_file(path, data_dir)
            if rec is None:
                continue
            # Skip nearly-empty stubs: need at least a name or description.
            if not rec["names"] and not rec["description_en"] and not rec["shlokas"]:
                continue
            candidates.append(rec)

    print(f"Parsed {len(candidates)} candidate festival files.")

    if limit is not None:
        candidates.sort(key=score, reverse=True)
        seen_ids = set()
        selected = []
        for rec in candidates:
            if rec["id"] in seen_ids:
                continue
            seen_ids.add(rec["id"])
            selected.append(rec)
            if len(selected) >= limit:
                break
    else:
        # dedupe by id, keep richest
        best_by_id = {}
        for rec in candidates:
            cur = best_by_id.get(rec["id"])
            if cur is None or score(rec) > score(cur):
                best_by_id[rec["id"]] = rec
        selected = list(best_by_id.values())

    print(f"Selected {len(selected)} festivals for the site.")

    out_dir = SITE_ROOT / "content" / "festivals"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.md"):
        f.unlink()

    used_slugs: dict[str, int] = {}
    for rec in selected:
        slug = slugify(rec["id"])
        if slug in used_slugs:
            used_slugs[slug] += 1
            slug = f"{slug}-{used_slugs[slug]}"
        else:
            used_slugs[slug] = 0

        title = None
        if rec["names"].get("sa"):
            title = rec["names"]["sa"][0]
        if not title:
            title = re.sub(r"[~_]+", " ", rec["id"])

        lines = ["+++"]
        lines.append(f"title = {toml_str(title)}")
        lines.append(f'id = {toml_str(rec["id"])}')
        lines.append(f"slug = {toml_str(slug)}")
        lines.append(f'source_path = {toml_str(rec["source_path"])}')
        if rec["tags"]:
            lines.append(f'tags = {toml_list(rec["tags"])}')
        if rec["devata"]:
            lines.append(f'devata = {toml_list(rec["devata"])}')
        if rec["month"]:
            lines.append(f'month = {toml_list(rec["month"])}')
        if rec["tithi"]:
            lines.append(f'tithi = {toml_list(rec["tithi"])}')
        if rec["nakshatra"]:
            lines.append(f'nakshatra = {toml_list(rec["nakshatra"])}')
        lines.append(f'category = {toml_list(rec["category"])}')
        if rec.get("kaala"):
            lines.append(f'kaala = {toml_str(rec["kaala"])}')
        if rec.get("priority"):
            lines.append(f'priority_rule = {toml_str(rec["priority"])}')
        if rec["timing_summary_parts"]:
            lines.append(
                f'timing_summary = {toml_str(", ".join(rec["timing_summary_parts"]))}'
            )
        if rec["references"]:
            lines.append(f'"references" = {toml_list(rec["references"])}')

        # NOTE: [names] must be the LAST section emitted. TOML has no way to
        # "close" a table back to root scope, so any scalar keys written
        # after a [table] header would be silently nested inside it.
        if rec["shlokas"]:
            lines.append("")
            lines.append(f"shlokas = {toml_multiline(rec['shlokas'])}")

        if rec["description_en"]:
            lines.append("")
            lines.append(f"description_en = {toml_multiline(rec['description_en'])}")

        if rec["names"]:
            lines.append("")
            lines.append("[names]")
            for lang, vals in rec["names"].items():
                lines.append(f"{lang} = {toml_list(vals)}")

        lines.append("+++")
        lines.append("")

        (out_dir / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(selected)} files to {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--limit", type=int, default=110, help="cap on number of festivals; use --all to disable")
    ap.add_argument("--all", action="store_true", help="build the full dataset instead of a curated subset")
    args = ap.parse_args()
    build(args.data_dir, None if args.all else args.limit)
