"""Complete, private organisation backups and an offline recovery verifier.

The restore command writes a new local recovery folder. It never connects to
production, imports accounts, overwrites files or changes credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 250
FORMAT = "werkstuur-organisation-backup-v1"


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _validate_payload(payload):
    org_id = payload.get("meta", {}).get("organization_id")
    if not isinstance(org_id, int) or isinstance(org_id, bool) or org_id < 1:
        raise ValueError("De backup mist een geldige organisatie.")
    if payload.get("organization", {}).get("id") != org_id:
        raise ValueError("De organisatiegegevens passen niet bij de backup.")
    case_ids = {row["id"] for row in payload.get("cases", [])}
    for table in ("customers", "support_tickets", "cases", "notes", "audit", "pilots", "pilot_snapshots"):
        for row in payload.get(table, []):
            if row.get("organization_id", org_id) != org_id:
                raise ValueError("De backup bevat gegevens van een andere organisatie.")
            if table in ("notes", "audit") and row.get("case_id") is not None and row["case_id"] not in case_ids:
                raise ValueError("Een dossierverwijzing ontbreekt in de backup.")
    seen = set()
    for row in payload.get("attachments", []):
        if row.get("id") in seen or row.get("case_id") not in case_ids:
            raise ValueError("Een bijlage is dubbel of hoort niet bij een dossier in de backup.")
        if not isinstance(row.get("id"), int) or not row.get("storage_path"):
            raise ValueError("Een bijlage mist een geldige bestandsverwijzing.")
        seen.add(row["id"])
    if any("password_hash" in row for row in payload.get("users", [])):
        raise ValueError("Wachtwoordgegevens horen niet in deze backup.")


def build_archive(payload, download):
    """Download every referenced private file, or fail without an incomplete ZIP."""
    _validate_payload(payload)
    attachments = payload.get("attachments", [])
    if len(attachments) > MAX_FILES:
        raise ValueError("Deze backup bevat meer dan 250 bijlagen. Maak kleinere deelbackups.")
    backup = _json_bytes(payload)
    total = len(backup)
    if total > MAX_BYTES:
        raise ValueError("De backup is groter dan 64 MB.")
    members = [{"path": "backup.json", "size": len(backup), "sha256": _digest(backup)}]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("backup.json", backup)
        for attachment in attachments:
            raw = download(attachment["storage_path"])
            if not isinstance(raw, bytes) or len(raw) != int(attachment.get("size_bytes", -1)):
                raise ValueError("Een bijlage kon niet volledig worden gelezen. De backup is niet aangemaakt.")
            total += len(raw)
            if total > MAX_BYTES:
                raise ValueError("Gegevens en bijlagen zijn samen groter dan 64 MB.")
            filename = re.sub(r"[^\w. -]", "_", Path(str(attachment.get("filename") or "bestand")).name)[:160]
            filename = filename.strip(" .") or "bestand"
            path = f"attachments/{attachment['id']}/{filename}"
            archive.writestr(path, raw)
            members.append({"path": path, "attachment_id": attachment["id"], "size": len(raw), "sha256": _digest(raw)})
        manifest = {"format": FORMAT, "organization_id": payload["meta"]["organization_id"],
                    "exported_at": payload["meta"].get("exported_at"), "files": members,
                    "contains_credentials": False, "includes_attachment_files": True}
        archive.writestr("manifest.json", _json_bytes(manifest))
    return out.getvalue()


def verify_archive(raw):
    """Validate limits, organisation boundaries, all hashes and all file references."""
    if len(raw) > MAX_BYTES + 2 * 1024 * 1024:
        raise ValueError("Het backupbestand is te groot.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) > MAX_FILES + 2 or len(set(names)) != len(names):
            raise ValueError("Ongeldige of dubbele bestanden in de backup.")
        if sum(info.file_size for info in infos) > MAX_BYTES + 1024 * 1024:
            raise ValueError("De uitgepakte backup is te groot.")
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Onveilig bestandspad in de backup.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT or not manifest.get("includes_attachment_files"):
            raise ValueError("Onbekend of onvolledig backupformaat.")
        members = manifest.get("files", [])
        listed = [member["path"] for member in members]
        if len(set(listed)) != len(listed) or set(listed) | {"manifest.json"} != set(names):
            raise ValueError("De bestandslijst is onvolledig of bevat dubbele verwijzingen.")
        content = {}
        for member in members:
            data = archive.read(member["path"])
            if len(data) != member["size"] or _digest(data) != member["sha256"]:
                raise ValueError("Een bestand is gewijzigd of beschadigd.")
            content[member["path"]] = data
        payload = json.loads(content["backup.json"])
        _validate_payload(payload)
        if manifest.get("organization_id") != payload["meta"]["organization_id"]:
            raise ValueError("De manifestorganisatie past niet bij de gegevens.")
        attachments = {row["id"]: row for row in payload.get("attachments", [])}
        file_members = [m for m in members if "attachment_id" in m]
        if len(file_members) != len(attachments) or {m["attachment_id"] for m in file_members} != set(attachments):
            raise ValueError("De backup mist een bijlagebestand.")
        for member in file_members:
            if member["size"] != int(attachments[member["attachment_id"]]["size_bytes"]):
                raise ValueError("Een bijlagegrootte past niet bij de dossiergegevens.")
        return payload, manifest, content


def restore_to_new_folder(raw, destination):
    payload, manifest, content = verify_archive(raw)
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Kies een nieuwe herstelmap; bestaande bestanden worden niet overschreven.")
    destination.mkdir(mode=0o700, parents=True)
    for name, data in {**content, "manifest.json": _json_bytes(manifest)}.items():
        path = destination / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("xb") as target:
            target.write(data)
        path.chmod(0o600)
    return {"organization_id": payload["meta"]["organization_id"],
            "cases": len(payload.get("cases", [])), "attachments": len(payload.get("attachments", [])),
            "checksums_verified": len(manifest["files"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Controleer en herstel een Werkstuur-backup in een nieuwe lokale map.")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args()
    raw = args.backup.read_bytes()
    if args.restore_to:
        result = restore_to_new_folder(raw, args.restore_to)
    else:
        payload, manifest, _ = verify_archive(raw)
        result = {"organization_id": payload["meta"]["organization_id"], "checksums_verified": len(manifest["files"])}
    print(json.dumps(result))
