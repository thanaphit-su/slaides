"""Transcript export formatters."""

import csv
import io
import json
from datetime import datetime


def transcript_to_csv(events: list[dict], total: int, exported_count: int, truncated: bool) -> str:
    """Convert transcript to CSV format with metadata header."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Metadata header row (commented)
    writer.writerow([f"# Transcript exported at {datetime.now().isoformat()}"])
    writer.writerow([f"# Total events: {total}, Exported: {exported_count}, Truncated: {truncated}"])
    writer.writerow(["timestamp", "event_type", "source", "participant_ref", "details"])
    
    for e in events:
        payload = e.get("payload", {})
        writer.writerow([
            e["occurred_at"],
            e["event_type"],
            e.get("source", ""),
            payload.get("participant_ref", ""),
            json.dumps(payload),
        ])
    
    return output.getvalue()


def transcript_to_json(events: list[dict], session_metadata: dict, total: int, truncated: bool) -> dict:
    """Convert transcript to .slaides-session JSON format with export metadata."""
    return {
        "version": "1.0",
        "session": session_metadata,
        "events": events,
        "export_metadata": {
            "total": total,
            "exported_count": len(events),
            "truncated": truncated,
            "exported_at": datetime.now().isoformat(),
        },
    }
