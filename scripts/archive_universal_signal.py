#!/usr/bin/env python3
"""Archive immuablement un dossier universel avant d'actualiser ``latest``.

Une archive contient le lot V2 complet : les signaux retenus, écartés et non
résolus restent ainsi disponibles pour les audits de calibration.  Le chemin
est déterminé par la date et l'identifiant du run.  Un second passage identique
est un succès sans écriture ; un contenu différent sous le même run est refusé.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

try:
    from scripts.run_deterministic_filters import validate_facts
except ModuleNotFoundError:  # pragma: no cover - direct workflow invocation.
    from run_deterministic_filters import validate_facts


CORE_SCHEMA = "lawradar-universal-signal-v2"
MANIFEST_SCHEMA = "lawradar-universal-signal-archive-v1"
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SHA256_VALUE = re.compile(r"^sha256:[0-9a-f]{64}$")
READING_FIELDS = {
    "consequence", "affected_actors", "beneficiaries", "constrained_parties",
    "potential_service_partners", "unknowns",
}
PREFILTER_LISTS = (
    "excluded_historical_candidates", "excluded_routine_candidates",
    "excluded_no_economic_friction_candidates",
    "deterministically_unresolved_candidates",
)
MONEY_FLOW_FIELDS = (
    "id", "label", "title", "money_sentence", "explanation", "payer",
    "recipient", "amount", "effective_date", "certainty", "next_action",
)


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _create_immutable(path: Path, content: bytes) -> str:
    """Publish through an exclusive hard link so an archive is never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"IMMUTABILITY_VIOLATION: {path}")
        return "NOOP"

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError(f"IMMUTABILITY_VIOLATION: {path}")
            return "NOOP"
        return "CREATED"
    finally:
        temporary.unlink(missing_ok=True)


def _validate_reading(
    signal: dict[str, Any], source_id: str, *, scenario_only: bool
) -> None:
    provenance = signal.get("reading_provenance")
    if not isinstance(provenance, dict) or set(provenance) != {
        "status", "basis", "producer", "source_id"
    }:
        raise ValueError("Provenance de lecture absente ou invalide.")
    if provenance.get("source_id") != source_id:
        raise ValueError("Lecture rattachée à une autre source.")
    reading = signal.get("reading")
    if provenance.get("status") == "MISSING_LEGACY":
        if reading is not None or provenance.get("basis") is not None or provenance.get("producer") != "LEGACY_COMPATIBILITY":
            raise ValueError("Lecture historique manquante présentée comme une analyse.")
        return
    producer = provenance.get("producer")
    if provenance.get("status") != "AVAILABLE" or provenance.get("basis") != "CANDIDATE_EVIDENCE_ONLY":
        raise ValueError("Provenance de lecture non prise en charge.")
    if producer == "SIMULATOR":
        source = signal.get("source")
        if not scenario_only or not isinstance(source, dict) or source.get("source_kind") != "SIMULATION":
            raise ValueError("Une lecture simulée ne peut pas être archivée comme production.")
    elif producer != "MOTOR_STRUCTURED_READING":
        raise ValueError("Producteur de lecture non pris en charge.")
    if not isinstance(reading, dict) or set(reading) != READING_FIELDS:
        raise ValueError("Lecture structurée absente ou invalide.")
    if not isinstance(reading.get("consequence"), str) or not reading["consequence"].strip():
        raise ValueError("Conséquence de lecture absente.")
    for name in READING_FIELDS - {"consequence"}:
        values = reading.get(name)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError(f"Champ de lecture invalide : {name}.")


def _validate_evidence(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError("Preuve compacte invalide.")
    if value.get("url") is not None and not isinstance(value.get("url"), str):
        raise ValueError("URL de preuve compacte invalide.")
    primary = value.get("primary_evidence")
    required = {
        "content_status", "text_sha256", "excerpt", "excerpt_truncated",
        "archive_url", "archive_sha256",
    }
    if not isinstance(primary, dict) or set(primary) != required:
        raise ValueError("Référence de preuve primaire incomplète.")
    excerpt = primary.get("excerpt")
    if excerpt is not None and (not isinstance(excerpt, str) or len(excerpt) > 2000):
        raise ValueError("Aperçu de preuve primaire invalide.")
    if not isinstance(primary.get("excerpt_truncated"), bool):
        raise ValueError("Indicateur de troncature invalide.")
    for name in ("content_status", "text_sha256", "archive_url", "archive_sha256"):
        if primary.get(name) is not None and not isinstance(primary.get(name), str):
            raise ValueError(f"Métadonnée de preuve invalide : {name}.")


def validate_dossier(
    dossier: dict[str, Any]
) -> tuple[date, str, str | None, list[dict[str, Any]]]:
    if dossier.get("schema") != CORE_SCHEMA:
        raise ValueError("L'archive attend un lawradar-universal-signal-v2.")
    run = dossier.get("run")
    if not isinstance(run, dict):
        raise ValueError("Bloc run absent du dossier universel.")
    for name in ("id", "url", "commit", "report_date"):
        if name not in run:
            raise ValueError(f"Champ run.{name} absent du dossier universel.")
    report_date = run.get("report_date")
    if not isinstance(report_date, str):
        raise ValueError("Date de rapport absente du dossier universel.")
    try:
        parsed_date = date.fromisoformat(report_date)
    except ValueError as error:
        raise ValueError("Date de rapport non ISO dans le dossier universel.") from error
    if parsed_date.isoformat() != report_date:
        raise ValueError("Date de rapport non canonique dans le dossier universel.")
    run_id = run.get("id")
    if not isinstance(run_id, str) or not SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError("Identifiant de run absent ou dangereux.")
    attempt = run.get("attempt")
    if attempt is not None and (
        not isinstance(attempt, str) or not attempt.isdigit() or int(attempt) < 1
    ):
        raise ValueError("Tentative de run invalide.")
    for name in ("url", "commit"):
        if run.get(name) is not None and not isinstance(run.get(name), str):
            raise ValueError(f"Champ run.{name} invalide.")
    context = dossier.get("context")
    if not isinstance(context, dict):
        raise ValueError("Contexte du dossier universel invalide.")
    prefilter = context.get("prefilter_audit")
    if not isinstance(prefilter, dict):
        raise ValueError("Audit du préfiltre absent du dossier universel.")
    for name in PREFILTER_LISTS:
        if not isinstance(prefilter.get(name), list):
            raise ValueError(f"Trace de préfiltre invalide : {name}.")
    signals = dossier.get("signals")
    if not isinstance(signals, list) or any(not isinstance(item, dict) for item in signals):
        raise ValueError("Liste de signaux invalide.")
    signal_ids: list[str] = []
    source_ids: list[str] = []
    source_to_signal: dict[str, str] = {}
    for signal in signals:
        signal_id = signal.get("id")
        source = signal.get("source")
        radar = signal.get("radar")
        identity = signal.get("identity")
        facts = signal.get("opportunity_facts")
        if not isinstance(signal_id, str) or not signal_id:
            raise ValueError("Chaque signal archivé doit porter un id.")
        if not isinstance(source, dict) or set(("source_id", "source_kind", "change", "evidence")) - set(source):
            raise ValueError("Chaque signal archivé doit porter un bloc source complet.")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Chaque signal archivé doit porter un source_id.")
        _validate_evidence(source.get("evidence"))
        if not isinstance(identity, dict) or not isinstance(identity.get("stable_source_id"), str) or not SHA256_VALUE.fullmatch(str(identity.get("evidence_version") or "")):
            raise ValueError("Identité stable ou version de preuve invalide.")
        if not isinstance(radar, dict) or radar.get("status") not in {"RETAINED", "DISCARDED", "UNRESOLVED"} or not isinstance(radar.get("reason"), (str, type(None))):
            raise ValueError("Décision Radar invalide.")
        if not isinstance(signal.get("enrichments"), dict):
            raise ValueError("Emplacements d'enrichissement absents.")
        if not isinstance(facts, dict):
            raise ValueError("Faits d'opportunité absents.")
        validate_facts(facts)
        if facts.get("signal_id") != signal_id:
            raise ValueError("Faits rattachés à un autre signal.")
        _validate_reading(
            signal, source_id, scenario_only=context.get("scenario_only") is True
        )
        signal_ids.append(signal_id)
        source_ids.append(source_id)
        source_to_signal[source_id] = signal_id
    if len(signal_ids) != len(set(signal_ids)):
        raise ValueError("Un id de signal est dupliqué dans le lot archivé.")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Un source_id est dupliqué dans le lot archivé.")
    flows = dossier.get("money_flows")
    if not isinstance(flows, list):
        raise ValueError("Flux financiers invalides.")
    flow_ids: set[str] = set()
    for flow in flows:
        if not isinstance(flow, dict) or any(
            not isinstance(flow.get(name), str) or not flow[name].strip()
            for name in MONEY_FLOW_FIELDS
        ):
            raise ValueError("Flux financier incomplet.")
        if flow["id"] in flow_ids:
            raise ValueError("Identifiant de flux financier dupliqué.")
        flow_ids.add(flow["id"])
        link_status = flow.get("link_status")
        source_id, signal_id = flow.get("source_id"), flow.get("signal_id")
        if link_status == "VERIFIED":
            if source_id not in source_to_signal or signal_id != source_to_signal[source_id]:
                raise ValueError("Flux financier rattaché au mauvais signal.")
        elif link_status == "UNRESOLVED_LEGACY":
            if source_id is not None or signal_id is not None:
                raise ValueError("Flux historique partiellement rattaché.")
        else:
            raise ValueError("Statut de liaison d'un flux financier invalide.")
    quality = dossier.get("quality")
    if not isinstance(quality, dict):
        raise ValueError("Bloc qualité absent.")
    expected_quality = {
        "opportunity_count": len(signals),
        "unresolved_count": sum(item["radar"]["status"] == "UNRESOLVED" for item in signals),
        "readings_available_count": sum(item["reading_provenance"]["status"] == "AVAILABLE" for item in signals),
        "money_flow_count": len(flows),
        "money_flow_unlinked_count": sum(item.get("link_status") != "VERIFIED" for item in flows),
        "evidence_reference_count": sum(
            bool((item.get("source", {}).get("evidence") or {}).get("url"))
            for item in signals
        ),
    }
    for name, expected in expected_quality.items():
        if quality.get(name) != expected:
            raise ValueError(f"Compteur qualité incohérent : {name}.")
    if not isinstance(quality.get("limitation"), str) or not quality["limitation"].strip():
        raise ValueError("Mesures qualité incomplètes.")
    return parsed_date, run_id, attempt, signals


def archive_dossier(
    dossier_path: Path,
    archive_root: Path,
    latest_path: Path | None,
    manifest_path: Path,
) -> dict[str, Any]:
    content = dossier_path.read_bytes()
    dossier = json.loads(content)
    if not isinstance(dossier, dict):
        raise ValueError("Le dossier universel doit être un objet JSON.")
    report_date, run_id, attempt, signals = validate_dossier(dossier)
    archive_name = f"run-{run_id}"
    if attempt is not None:
        archive_name += f"-attempt-{attempt}"
    archive_path = (
        archive_root / "v2" / f"{report_date.year:04d}" / f"{report_date.month:02d}"
        / f"{archive_name}.json"
    )
    status = _create_immutable(archive_path, content)
    digest = hashlib.sha256(content).hexdigest()
    signal_refs = []
    for signal in signals:
        identity = signal.get("identity") if isinstance(signal.get("identity"), dict) else {}
        signal_refs.append({
            "signal_id": signal.get("id"),
            "stable_source_id": identity.get("stable_source_id"),
            "evidence_version": identity.get("evidence_version"),
            "source_id": signal["source"]["source_id"],
            "radar_status": (signal.get("radar") or {}).get("status"),
        })
    durable_manifest_path = archive_path.with_suffix(".manifest.json")
    durable_manifest = {
        "schema": MANIFEST_SCHEMA,
        "status": "ARCHIVED",
        "run_id": run_id,
        "run_attempt": attempt,
        "report_date": report_date.isoformat(),
        "archive_path": archive_path.as_posix(),
        "sha256": digest,
        "signal_count": len(signals),
        "prefilter_counts": {
            name: len(dossier["context"]["prefilter_audit"][name])
            for name in PREFILTER_LISTS
        },
        "signals": signal_refs,
    }
    durable_status = _create_immutable(
        durable_manifest_path,
        (json.dumps(durable_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )

    # ``latest`` is only a convenience pointer. Successful model deliveries
    # move it after both immutable files exist. Archive-only runs preserve
    # prefilter calibration without replacing the last usable client core.
    if latest_path is not None:
        _atomic_replace(latest_path, content)
    manifest = {
        **durable_manifest,
        "status": status,
        "durable_manifest_status": durable_status,
        "durable_manifest_path": durable_manifest_path.as_posix(),
        "latest_path": latest_path.as_posix() if latest_path is not None else None,
    }
    _atomic_replace(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=Path("evidence/universal-signals"))
    parser.add_argument("--latest", type=Path, default=Path("evidence/universal-signal-latest.json"))
    parser.add_argument(
        "--archive-only", action="store_true",
        help="Archive le dossier sans déplacer le pointeur latest.",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = archive_dossier(
        args.dossier, args.archive_root,
        None if args.archive_only else args.latest, args.manifest,
    )
    print(json.dumps({
        "status": manifest["status"],
        "archive_path": manifest["archive_path"],
        "durable_manifest_path": manifest["durable_manifest_path"],
        "sha256": manifest["sha256"],
        "signal_count": manifest["signal_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
