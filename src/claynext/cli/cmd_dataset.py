"""CLI: dialogue localization datasets (import, validate, dedupe, split, report, version, export)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from claynext.cli.common import die, require_file


def add_parser(sub: argparse._SubParsersAction) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--name", required=True, help="Dataset name (folder under data/datasets)")
    common.add_argument("--root", help="Datasets root (default: data/datasets)")

    p = sub.add_parser("dataset", help="Khmer dialogue localization datasets")
    ds = p.add_subparsers(dest="dataset_command", required=True)

    imp = ds.add_parser("import", parents=[common], help="Import CSV / JSON / JSONL into the working set")
    imp.add_argument("input", help="Input .csv / .json / .jsonl")
    imp.add_argument("--replace", action="store_true", help="Replace the working set instead of appending")
    imp.add_argument("--source-name", default="", help="Provenance dataset name (default: input folder name)")
    imp.set_defaults(func=run_import)

    val = ds.add_parser("validate", parents=[common], help="Validate records against the schema rules")
    val.add_argument("--version", default="working", help="working | latest | vNNNN")
    val.add_argument("--show", type=int, default=10, help="Print the first N records with errors")
    val.set_defaults(func=run_validate)

    dd = ds.add_parser("dedupe", parents=[common], help="Find exact and near duplicates")
    dd.add_argument("--field", choices=["target", "source"], default="target")
    dd.add_argument("--threshold", type=float, default=0.8, help="Near-duplicate Jaccard threshold")
    dd.add_argument("--drop-exact", action="store_true", help="Remove exact duplicates from the working set")
    dd.set_defaults(func=run_dedupe)

    sp = ds.add_parser("split", parents=[common], help="Group-aware train / validation / test split")
    sp.add_argument("--seed", type=int, default=13)
    sp.add_argument("--ratios", default="0.8,0.1,0.1", help="train,validation,test")
    sp.add_argument("--group-keys", default="film_id,script_id,dialogue_family,speaker_id",
                    help="Group key priority (first present key wins)")
    sp.add_argument("--no-merge-near", action="store_true",
                    help="Do not merge groups that share near-duplicate clusters")
    sp.add_argument("--threshold", type=float, default=0.8, help="Near-duplicate threshold for merging")
    sp.set_defaults(func=run_split)

    rp = ds.add_parser("report", parents=[common], help="Dataset quality report")
    rp.add_argument("--version", default="working", help="working | latest | vNNNN")
    rp.add_argument("--json", action="store_true", help="Print JSON")
    rp.add_argument("--threshold", type=float, default=0.8)
    rp.set_defaults(func=run_report)

    vs = ds.add_parser("version", parents=[common], help="Snapshot the working set as an immutable version")
    vs.add_argument("--note", default="")
    vs.add_argument("--allow-unchanged", action="store_true")
    vs.add_argument("--list", action="store_true", help="List versions instead of creating one")
    vs.set_defaults(func=run_version)

    ex = ds.add_parser("export", parents=[common], help="Export canonical JSONL or chat SFT files")
    ex.add_argument("--version", default="latest", help="working | latest | vNNNN")
    ex.add_argument("--format", choices=["jsonl", "sft"], default="sft")
    ex.add_argument("-o", "--output", help="Output file (jsonl) or folder (sft). Default: data/outputs/datasets/...")
    ex.add_argument("--include-unreviewed", action="store_true",
                    help="SFT: also export draft / staging records (labelled unreviewed in the manifest)")
    ex.set_defaults(func=run_export)

    re_ = ds.add_parser("review-export", parents=[common], help="Write a CSV review sheet for native reviewers")
    re_.add_argument("--version", default="working", help="working | latest | vNNNN")
    re_.add_argument("--status", default="draft,staging",
                     help="Comma-separated statuses to include (default: draft,staging; 'all' for every record)")
    re_.add_argument("--category", default="", help="Comma-separated categories to include")
    re_.add_argument("--split", default="", help="Comma-separated splits to include")
    re_.add_argument("--out", help="Output .csv (default: data/outputs/datasets/<name>/review/...)")
    re_.set_defaults(func=run_review_export)

    rv = ds.add_parser("review-apply", parents=[common], help="Apply a filled review sheet (CSV/JSON/JSONL)")
    rv.add_argument("input", help="Review sheet from review-export, or review_template.csv")
    rv.add_argument("--reviewed-at", help="ISO timestamp for rows whose reviewed_at cell is empty (default: now)")
    rv.set_defaults(func=run_review_apply)

    pr = ds.add_parser("promote", parents=[common], help="Promote records to staging / reviewed / gold")
    pr.add_argument("--to", required=True, choices=["staging", "reviewed", "gold"])
    pr.add_argument("--ids", action="append", default=[],
                    help="Record ids (comma-separated, repeatable). Default: every record that could move")
    pr.add_argument("--require-license", action=argparse.BooleanOptionalAction, default=None,
                    help="Require provenance.license (default: on for gold, off otherwise; gold always needs it)")
    pr.add_argument("--by", default="", help="Pseudonymous id of the person promoting (audit trail)")
    pr.add_argument("--dry-run", action="store_true", help="Report only; do not change the working set")
    pr.set_defaults(func=run_promote)


def _store(args: argparse.Namespace):
    from claynext.models.datasets.store import DatasetStore

    try:
        return DatasetStore(args.name, root=args.root)
    except ValueError as exc:
        die(str(exc))


def _load(store, version: str):
    try:
        if version == "working":
            return store.load_working(), "working"
        if version == "latest":
            latest = store.latest_version()
            if latest is None:
                die(f"dataset {store.name!r} has no versions; run 'claynext dataset version --name {store.name}'")
            version = latest
        return store.load_version(version), version
    except FileNotFoundError as exc:
        die(str(exc))


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def run_import(args: argparse.Namespace) -> int:
    store = _store(args)
    path = require_file(args.input, label="input")
    try:
        result = store.import_file(path, replace=args.replace, source_name=args.source_name)
    except ValueError as exc:
        die(str(exc))
    _print_json({"dataset": store.name, "working_set": str(store.working_path), **result.summary()})
    return 0


def run_validate(args: argparse.Namespace) -> int:
    from claynext.models.datasets.schema import validate_record

    store = _store(args)
    records, label = _load(store, args.version)
    errors: dict[str, int] = {}
    warnings: dict[str, int] = {}
    shown = 0
    for rec in records:
        issues = validate_record(rec)
        for issue in issues:
            bucket = errors if issue.severity == "error" else warnings
            bucket[issue.code] = bucket.get(issue.code, 0) + 1
        bad = [i for i in issues if i.severity == "error"]
        if bad and shown < args.show:
            shown += 1
            print(f"{rec.id}: " + "; ".join(f"{i.code} ({i.field})" for i in bad))
    _print_json({"dataset": store.name, "version": label, "records": len(records),
                 "errors": dict(sorted(errors.items())), "warnings": dict(sorted(warnings.items()))})
    return 1 if errors else 0


def run_dedupe(args: argparse.Namespace) -> int:
    from claynext.models.datasets.dedupe import drop_exact_duplicates, find_duplicates

    store = _store(args)
    records, _ = _load(store, "working")
    report = find_duplicates(records, which=args.field, threshold=args.threshold)
    data = {"summary": report.summary(), **report.to_dict(), "near_clusters": report.near_clusters}
    if args.drop_exact:
        kept, dropped = drop_exact_duplicates(records, which=args.field)
        store.save_working(kept)
        data["dropped"] = dropped
    store.save_report("dedupe", data)
    _print_json({"dataset": store.name, **report.summary(), "dropped": len(data.get("dropped", []))})
    return 0


def run_split(args: argparse.Namespace) -> int:
    from claynext.models.datasets.dedupe import find_duplicates
    from claynext.models.datasets.split import apply_split, find_leaks, split_records

    store = _store(args)
    records, _ = _load(store, "working")
    try:
        ratios = tuple(float(x) for x in args.ratios.split(","))
        keys = tuple(k.strip() for k in args.group_keys.split(",") if k.strip())
        clusters = None if args.no_merge_near else find_duplicates(records, threshold=args.threshold).near_clusters
        report = split_records(records, ratios=ratios, seed=args.seed, group_keys=keys, near_clusters=clusters)
    except ValueError as exc:
        die(str(exc))
    apply_split(records, report)
    leaks = find_leaks(records, group_keys=keys, near_clusters=clusters)
    if leaks:
        die(f"split leaked {len(leaks)} group(s); working set not changed")
    store.save_working(records)
    store.save_report("split", {"split": report.to_dict(), "leaks": leaks})
    _print_json({"dataset": store.name, **report.to_dict(), "leaks": len(leaks)})
    return 0


def run_report(args: argparse.Namespace) -> int:
    from claynext.models.datasets.dedupe import find_duplicates
    from claynext.models.datasets.report import format_report, quality_report

    store = _store(args)
    records, label = _load(store, args.version)
    dup = find_duplicates(records, threshold=args.threshold)
    report = quality_report(records, duplicates=dup, near_clusters=dup.near_clusters)
    report["version"] = label
    if label == "working":
        store.save_report("report", report)
    if args.json:
        _print_json(report)
    else:
        print(f"dataset {store.name} ({label})")
        print(format_report(report))
    return 0


def run_version(args: argparse.Namespace) -> int:
    store = _store(args)
    if args.list:
        rows = []
        for v in store.list_versions():
            m = store.manifest(v)
            rows.append({k: m.get(k) for k in ("version", "parent", "created_at", "record_count", "sha256", "note")}
                        | {"intact": store.verify_version(v)})
        _print_json(rows)
        return 0
    try:
        manifest = store.create_version(note=args.note, allow_unchanged=args.allow_unchanged)
    except (FileNotFoundError, ValueError) as exc:
        die(str(exc))
    _print_json(manifest)
    return 0


def run_export(args: argparse.Namespace) -> int:
    from claynext.models.datasets.export import TRAINING_STATUSES, export_jsonl, export_sft
    from claynext.utils.paths import OUTPUTS_DIR

    store = _store(args)
    records, label = _load(store, args.version)
    base = OUTPUTS_DIR / "datasets" / store.name / label
    if args.format == "jsonl":
        out = Path(args.output) if args.output else base / "records.jsonl"
        print(export_jsonl(records, out))
        return 0
    statuses = TRAINING_STATUSES + (("draft", "staging") if args.include_unreviewed else ())
    out = Path(args.output) if args.output else base / "sft"
    source = {"dataset": store.name, "version": label}
    if label != "working":
        source["sha256"] = store.manifest(label)["sha256"]
    manifest = export_sft(records, out, statuses=statuses, source=source)
    _print_json({"output": str(out), **{k: manifest[k] for k in ("examples", "skipped_by_status",
                                                                   "contains_unreviewed", "files")}})
    if manifest["examples"] == 0:
        print("note: no records matched; only reviewed / gold records are exported unless --include-unreviewed")
    return 0


def run_review_apply(args: argparse.Namespace) -> int:
    from claynext.models.datasets.review import apply_review_file
    from claynext.models.datasets.schema import parse_iso

    store = _store(args)
    path = require_file(args.input, label="review sheet")
    records, _ = _load(store, "working")
    if args.reviewed_at and parse_iso(args.reviewed_at) is None:
        die(f"--reviewed-at {args.reviewed_at!r} is not ISO 8601")
    result = apply_review_file(records, path, reviewed_at=args.reviewed_at)
    store.save_working(records)
    _print_json({"dataset": store.name, **result.to_dict()})
    if result.timestamp_source.get("clock"):
        print(f"note: {result.timestamp_source['clock']} row(s) had no reviewed_at; apply time was used",
              file=sys.stderr)
    return 1 if result.errors else 0


def _csv_set(value: str) -> set[str]:
    return {v.strip() for v in (value or "").split(",") if v.strip()}


def run_review_export(args: argparse.Namespace) -> int:
    from claynext.models.datasets.review import SHEET_COLUMNS, export_review_sheet
    from claynext.models.datasets.store import now_iso
    from claynext.utils.paths import OUTPUTS_DIR

    store = _store(args)
    records, label = _load(store, args.version)
    statuses = _csv_set(args.status)
    categories, splits = _csv_set(args.category), _csv_set(args.split)
    chosen = [
        r for r in records
        if ("all" in statuses or r.status in statuses)
        and (not categories or r.category in categories)
        and (not splits or r.split in splits)
    ]
    stamp = now_iso().replace(":", "").replace("+0000", "Z")
    out = Path(args.out) if args.out else OUTPUTS_DIR / "datasets" / store.name / "review" / f"review_{label}_{stamp}.csv"
    path = export_review_sheet(chosen, out)
    _print_json({"dataset": store.name, "version": label, "rows": len(chosen), "output": str(path),
                 "columns": len(SHEET_COLUMNS)})
    return 0


def run_promote(args: argparse.Namespace) -> int:
    from claynext.models.datasets.promote import promote_records

    store = _store(args)
    records, _ = _load(store, "working")
    ids = sorted({i for chunk in args.ids for i in _csv_set(chunk)})
    if args.to == "gold" and args.require_license is False:
        print("note: gold always requires a license (schema rule); --no-require-license is ignored",
              file=sys.stderr)
    result = promote_records(records, args.to, ids=ids or None, require_license=args.require_license,
                             by=args.by or None, dry_run=args.dry_run)
    if result.promoted and not args.dry_run:
        store.save_working(records)
    _print_json({"dataset": store.name, "dry_run": args.dry_run, **result.to_dict()})
    return 1 if result.blocked or result.unknown_ids else 0
