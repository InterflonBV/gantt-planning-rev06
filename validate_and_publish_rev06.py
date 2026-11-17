#!/usr/bin/env python3
"""REV06: publish ONLY explicitly selected and current Wrike items.

Input: repository_dispatch client_payload {"schema":"interflon-stakeholder-gantt-v2",
"items":[{wrikeId,name,itemType,status,startDate,dueDate,parentWrikeId,
showInGantt:true,inCurrentExport:true}],"milestones":[]}.
The list must be prefiltered in Power Automate; this script enforces each flag.
Never copy raw SharePoint records, hierarchyPath, Location, or private metadata.
"""
import datetime
import json
import os
import re
from pathlib import Path

SCHEMA = "interflon-stakeholder-gantt-v2"
TYPES = {"Project", "Folder", "Task"}


def fail(message):
    raise ValueError(message)


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def build(payload):
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        fail("Ongeldig REV06-publicatieformaat")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        fail("Geen aangevinkte Wrike-onderdelen ontvangen; publicatie geblokkeerd")
    if len(raw_items) > 1500:
        fail("Te veel geselecteerde onderdelen")
    if payload.get("milestones", []) != []:
        fail("REV06-mijlpalen zijn nog niet ingeschakeld")

    by_id = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            fail("Ongeldig Wrike-onderdeel")
        if raw.get("showInGantt") is not True or raw.get("inCurrentExport") is not True:
            fail("Publicatie geblokkeerd: item is niet expliciet geselecteerd en actueel")
        wid = str(raw.get("wrikeId") or "").strip()
        name = str(raw.get("name") or "").strip()
        item_type = raw.get("itemType")
        if not re.fullmatch(r"\d+", wid) or wid in by_id:
            fail("Ongeldige of dubbele Wrike-ID: " + wid)
        if not name or len(name) > 250 or item_type not in TYPES:
            fail("Ongeldige naam of type voor Wrike-ID " + wid)
        status = str(raw.get("status") or "").strip()[:80]
        start = str(raw.get("startDate") or "").strip()
        due = str(raw.get("dueDate") or "").strip()
        parent = str(raw.get("parentWrikeId") or "").strip()
        if parent and not re.fullmatch(r"\d+", parent):
            fail("Ongeldig parentWrikeId: " + wid)
        if item_type != "Folder":
            if not valid_date(start) or not valid_date(due) or due < start:
                fail("Geselecteerd Project/Task heeft geen geldige periode: " + name)
        # Folders are grouping rows, never date bars; do not publish source dates.
        by_id[wid] = {"wrikeId": wid, "name": name, "itemType": item_type,
                      "status": status, "startDate": start if item_type != "Folder" else "",
                      "dueDate": due if item_type != "Folder" else "",
                      "parentWrikeId": parent}

    # Hidden ancestors are intentionally omitted. Do not publish their IDs/names/path.
    for wid, item in by_id.items():
        if item["parentWrikeId"] not in by_id:
            item["parentWrikeId"] = ""
        if item["parentWrikeId"] == wid:
            fail("Zelfverwijzende hiërarchie: " + wid)
    for wid in by_id:
        visited = {wid}
        parent = by_id[wid]["parentWrikeId"]
        while parent:
            if parent in visited:
                fail("Cirkel in geselecteerde hiërarchie: " + wid)
            visited.add(parent)
            parent = by_id[parent]["parentWrikeId"]

    return {"schema": SCHEMA,
            "publishedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "items": list(by_id.values()), "milestones": []}


if __name__ == "__main__":
    payload = os.environ.get("GANTT_DISPATCH_PAYLOAD")
    if not payload:
        fail("GANTT_DISPATCH_PAYLOAD ontbreekt")
    out = build(json.loads(payload))
    Path("gantt-data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("REV06 gevalideerd: ", len(out["items"]), "zichtbare onderdelen, 0 mijlpalen")
