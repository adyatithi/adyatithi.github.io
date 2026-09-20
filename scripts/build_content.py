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

from indic_transliteration import sanscript

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def to_iast(text: str) -> str:
    """Convert Harvard-Kyoto-scheme text to IAST.

    Source ids and some name languages (ta, hi, ...) are stored in HK ASCII
    per adyatithi convention. Devanagari text (sa names, shlokas) is passed
    through untouched — running it through the HK transliterator would
    misinterpret the unicode codepoints.
    """
    if not text or DEVANAGARI_RE.search(text):
        return text
    # jyotisha's id/name generator uses its own HK_DRAVIDIAN scheme, an
    # extended HK that distinguishes short/long e & o (capital E/O = dirgha
    # e/o) for Dravidian-language names — plain HK doesn't know this
    # convention and leaves stray capital E/O untransliterated.
    return sanscript.transliterate(text, sanscript.roman.HK_DRAVIDIAN, sanscript.IAST)


def clean_text(text: str) -> str:
    """Typographic cleanup for shlokas/descriptions: the source data uses a
    bare '---' as an inline citation marker (e.g. 'अग्निपुराणे---' or
    '---धर्मसिन्धौ'); render it as a proper em dash."""
    if not text:
        return text
    return re.sub(r"-{3,}", "—", text)


# Ordered: first matching pattern wins. Matched case-insensitively against
# each raw references_primary/references_secondary string. This collapses
# ~157 raw citation strings (many differing only by page number, or an
# author-name vs. title alias for the same nibandha) down to ~38 real
# sources, so "cited by N festivals" and a "popular sources" list are
# actually meaningful.
SOURCE_ALIASES = [
    (r"smriti\s*muktaphal|smrti\s*mukthaphal|vaidyan[aā]tha[\s\-]*d[iī]k[sṣ]h?it[iī]y", "Smṛtimuktāphala (Vaidyanātha Dīkṣita)"),
    (r"smriti\s*kaustub", "Smṛtikaustubha (Anantadeva)"),
    (r"puru[sṣ]?[aā]?rtha\s*chintamani|purushartha\s*chintamani", "Puruṣārthacintāmaṇi"),
    (r"nirnaya\s*sind[hu]|nirnay\s*sagar", "Nirṇayasindhu (Kamalākarabhaṭṭa)"),
    (r"naradiya?\s*pur[aā]?nam?|narada\s*puran|narada\s*purnam", "Nārada Purāṇa"),
    (r"krtyas[aā]rasamu?c{1,2}h?ay|krutyasa+ra\s*samucchayam|kṛtyas", "Kṛtyasārasamuccaya"),
    (r"chaturvar[ag]a\s*chintamani|chaturvaga\s*chintamani|hemadri", "Caturvargacintāmaṇi (Hemādri)"),
    (r"skanda\s*puran", "Skanda Purāṇa"),
    (r"padma\s*puran", "Padma Purāṇa"),
    (r"nilamata\s*puran", "Nīlamata Purāṇa"),
    (r"bhavishyottara\s*puran", "Bhaviṣyottara Purāṇa"),
    (r"bhavish?ya?t?\s*puran", "Bhaviṣya Purāṇa"),
    (r"satyavrata\s*smriti", "Satyavrata Smṛti"),
    (r"vrata\s*ch[uū]d[aā]ma[nṇ]i", "Vratacūḍāmaṇi"),
    (r"kurma\s*puran", "Kūrma Purāṇa"),
    (r"mahabharat", "Mahābhārata"),
    (r"dharma\s*sindhu|dharmasindhu", "Dharmasindhu (Kāśīnātha Upādhyāya)"),
    (r"^vrataraja$|vrata\s*raja\s*p\.", "Vratarāja"),
    (r"vrata\s*nirnaya\s*kalpavalli", "Vratanirṇayakalpavallī"),
    (r"^63\s*nayanmar\s*saints", "63 Nayanmār Saints (Swami Sivananda)"),
    (r"kielhorn", "Kielhorn (1897)"),
    (r"vaidikasri", "Vaidikaśrī (periodical)"),
    (r"kamakoti\.org", "kamakoti.org"),
    (r"hindupad\.com", "Hindupad.com"),
    (r"aama.{0,4}jyotishi", "Āmār Jyotiṣī (regional pañcāṅga)"),
    (r"garga\s*samhita", "Gargasaṃhitā"),
    (r"lakshmi\s*narayana\s*samhita", "Lakṣmīnārāyaṇa Saṃhitā"),
    (r"markandeya\s*samhita", "Mārkaṇḍeya Saṃhitā"),
    (r"vrat\s*parichay", "Vrat Parichay"),
    (r"vrata\s*mahima", "Vrata Mahima"),
    (r"twitter\.com", "Twitter/X post"),
    (r"festivalsofindia\.in", "FestivalsOfIndia.in"),
    (r"jansatta\.com", "Jansatta.com"),
    (r"mahaperiyavaa\.blog", "mahaperiyavaa.blog"),
    (r"shishtaachaara|shishtachara", "Śiṣṭācāra (customary practice)"),
    (r"punya\s*shloka\s*manjari", "Puṇyaślokamañjarī"),
]


def canonicalize_source(raw: str) -> str:
    s = raw.strip().strip("`")
    for pattern, canon in SOURCE_ALIASES:
        if re.search(pattern, s, re.IGNORECASE):
            return canon
    m = re.match(r"https?://([^/]+)/?", s)
    if m:
        return m.group(1)
    return s


def clean_name(text: str) -> str:
    """IAST-transliterate (if applicable) and strip the '~' / '_' compound-
    word joiners used throughout the source data (in both Devanagari and HK
    fields) — a display artifact, not meant to be shown to readers."""
    return re.sub(r"[~_]+", " ", to_iast(text)).strip()


SITE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = Path(
    "/home/karthik/GitHub/jyotisha/jyotisha/panchaanga/temporal/festival/data"
)

# Only these top-level dirs are treated as "festival" content for the site.
INCLUDED_ROOTS = [
    "general",
    "devatA",
    "tamil",
    "temples",
    "gRhya",
    "time_focus",
    "mahApuruSha",
]

# Specific subtrees to skip even within an included root. xatra-later holds
# grim modern-history entries (massacres, persecution) that aren't festival
# content and don't belong in this showcase.
EXCLUDED_SUBPATHS = {
    ("mahApuruSha", "xatra-later"),
}

CATEGORY_META = {
    "general": ("General Observances", "Pan-Hindu vratas, festivals and special days."),
    "devatA": ("Devatā Observances", "Festivals organized by the presiding deity."),
    "tamil": ("Tamil Traditions", "Festivals and observances from Tamil tradition."),
    "temples": ("Temple Festivals", "Festivals tied to specific temples and regions."),
    "gRhya": ("Gṛhya Rites", "Household-rite (gṛhyasūtra) observances."),
    "time_focus": ("Calendrical Specials", "Observances defined by rare or recurring time-patterns."),
    "mahApuruSha": ("Mahāpuruṣa Observances", "Jayantis and commemorations of saints, ācāryas and sages."),
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

# mahApuruSha immediate subfolder -> display name for the "tradition" taxonomy.
TRADITION_META = {
    "ALvAr": "Āḻvār",
    "nAyanmAr": "Nāyanmār",
    "kAnchI-maTha": "Kāñcī Maṭha",
    "zRGgErI-maTha": "Śṛṅgeri Maṭha",
    "RShi": "Ṛṣi",
    "vaiShNava-misc": "Vaiṣṇava Ācāryas",
    "smArta-misc": "Smārta Ācāryas",
    "mAdhva-misc": "Mādhva Ācāryas",
    "sangIta-kRt": "Composers (Saṅgīta-kṛt)",
    "sci-tech": "Science & Technology",
    "xatra": "Kings & Dynasties",
    "general-indic-tropical": "General",
    "general-indic-non-tropical": "General",
}


# month_type == "lunar_month": Sanskrit lunar (candra) months, Caitra-start.
MONTHS = {
    1: ("Caitra", "चैत्र"), 2: ("Vaiśākha", "वैशाख"), 3: ("Jyeṣṭha", "ज्येष्ठ"),
    4: ("Āṣāḍha", "आषाढ"), 5: ("Śrāvaṇa", "श्रावण"), 6: ("Bhādrapada", "भाद्रपद"),
    7: ("Āśvina", "आश्विन"), 8: ("Kārtika", "कार्तिक"), 9: ("Mārgaśira", "मार्गशिर"),
    10: ("Pauṣa", "पौष"), 11: ("Māgha", "माघ"), 12: ("Phālguna", "फाल्गुन"),
}

# month_type in {"sidereal_solar_month", "tropical", "solar_month"}: solar
# months / rāśi, Meṣa-start. Distinct from the lunar months above — e.g.
# tiruvaNNAmalai dIpam (Kārthigai Dīpam) is sidereal_solar_month 8 = Vṛścika,
# NOT the lunar month Kārtika, even though the English names look similar.
RASHIS = {
    1: ("Meṣa", "मेष"), 2: ("Vṛṣabha", "वृषभ"), 3: ("Mithuna", "मिथुन"),
    4: ("Karka", "कर्क"), 5: ("Siṃha", "सिंह"), 6: ("Kanyā", "कन्या"),
    7: ("Tulā", "तुला"), 8: ("Vṛścika", "वृश्चिक"), 9: ("Dhanu", "धनु"),
    10: ("Makara", "मकर"), 11: ("Kumbha", "कुम्भ"), 12: ("Mīna", "मीन"),
}

# month_type in {"gregorian", "julian"}: plain calendar months, unrelated to
# any Hindu calendrical unit — kept out of the month/rashi taxonomies.
GREGORIAN_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

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

    references_raw = doc.get("references_primary", []) + doc.get("references_secondary", [])

    record: dict = {
        "id": fid,
        "source_path": str(rel),
        "tags": doc.get("tags", []),
        "shlokas": clean_text((doc.get("shlokas") or "").strip()),
        "description_en": clean_text(((doc.get("description") or {}).get("en") or "").strip()),
        "names": {
            k: [clean_name(x) for x in v]
            for k, v in (doc.get("names") or {}).items()
            if v
        },
        # raw citation strings, exactly as written (kept for display, with
        # page numbers etc. intact) -- was references_secondary-only before,
        # silently dropping every references_primary citation.
        "references": references_raw,
        # deduped canonical source names, for cross-linking/browsing
        "sources": list(dict.fromkeys(canonicalize_source(x) for x in references_raw)),
    }

    timing = doc.get("timing") or {}
    month_type = timing.get("month_type")
    month_num = timing.get("month_number")
    anga_type = timing.get("anga_type")
    anga_number = timing.get("anga_number")

    record["month"] = []
    record["rashi"] = []
    record["tithi"] = []
    record["nakshatra"] = []
    record["timing_summary_parts"] = []

    if month_type == "lunar_month" and isinstance(month_num, int) and month_num in MONTHS:
        iast, deva = MONTHS[month_num]
        # Zero-padded number prefix on the TAXONOMY VALUE only (not the
        # prose timing_summary sentence below): this both labels the pill
        # with its calendar position and makes plain alphabetical sort
        # (what Hugo's taxonomy .Alphabetical uses) come out in the correct
        # Caitra->Phalguna / Mesha->Mina order for free.
        record["month"] = [f"{month_num:02d}. {iast}"]
        record["timing_summary_parts"].append(f"{iast} ({deva}) māsa")
    elif (
        month_type in ("sidereal_solar_month", "tropical", "solar_month")
        and isinstance(month_num, int)
        and month_num in RASHIS
    ):
        iast, deva = RASHIS[month_num]
        record["rashi"] = [f"{month_num:02d}. {iast}"]
        qualifier = "tropical" if month_type == "tropical" else "sidereal"
        record["timing_summary_parts"].append(f"{iast} ({deva}) māsa, {qualifier}")
    elif (
        month_type in ("gregorian", "julian")
        and isinstance(month_num, int)
        and 1 <= month_num <= 12
    ):
        # Plain calendar date, not a Hindu calendrical unit: goes into the
        # timing summary text only, not the month/rashi taxonomies.
        mname = GREGORIAN_MONTHS[month_num - 1]
        cal_label = "Julian calendar" if month_type == "julian" else "Gregorian calendar"
        if anga_type == "day" and isinstance(anga_number, int):
            record["timing_summary_parts"].append(f"{mname} {anga_number} ({cal_label})")
            anga_type = None  # already consumed above; skip the anga block below
        else:
            record["timing_summary_parts"].append(f"{mname} ({cal_label})")

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

    # devata: immediate child folder under devatA/
    record["devata"] = []
    if root == "devatA" and len(parts) > 2:
        key = parts[1]
        record["devata"] = [DEVATA_META.get(key, to_iast(key))]

    # tradition: immediate child folder under mahApuruSha/
    record["tradition"] = []
    if root == "mahApuruSha" and len(parts) > 2:
        key = parts[1]
        record["tradition"] = [TRADITION_META.get(key, to_iast(key))]

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
            rel_parts = path.relative_to(data_dir).parts
            if any(rel_parts[: len(ex)] == ex for ex in EXCLUDED_SUBPATHS):
                continue
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

        id_display = clean_name(rec["id"])

        title = None
        if rec["names"].get("sa"):
            title = rec["names"]["sa"][0]
        if not title:
            title = id_display

        lines = ["+++"]
        lines.append(f"title = {toml_str(title)}")
        lines.append(f'id = {toml_str(rec["id"])}')
        lines.append(f"id_display = {toml_str(id_display)}")
        lines.append(f"slug = {toml_str(slug)}")
        lines.append(f'source_path = {toml_str(rec["source_path"])}')
        if rec["tags"]:
            lines.append(f'tags = {toml_list(rec["tags"])}')
        if rec["devata"]:
            lines.append(f'devata = {toml_list(rec["devata"])}')
        if rec["tradition"]:
            lines.append(f'tradition = {toml_list(rec["tradition"])}')
        if rec["month"]:
            lines.append(f'month = {toml_list(rec["month"])}')
        if rec["rashi"]:
            lines.append(f'rashi = {toml_list(rec["rashi"])}')
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
        if rec["sources"]:
            lines.append(f'sources = {toml_list(rec["sources"])}')

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
