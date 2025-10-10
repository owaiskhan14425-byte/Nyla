import os
import json

def read_log_as_json(log_path, limit=100):
    """
    Reads the last `limit` JSON lines from the log file, parses them as dicts.
    Returns a list of dicts.
    """
    logs = []
    if not os.path.isfile(log_path):
        return logs

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Reverse to get most recent first if desired
    lines = lines[::-1]

    count = 0
    for line in lines:
        # Find first `{` after log preamble
        json_start = line.find("{")
        if json_start != -1:
            try:
                log_json = json.loads(line[json_start:])
                logs.append(log_json)
                count += 1
                if count >= limit:
                    break
            except Exception:
                continue  # Skip non-JSON or malformed lines
    return logs


def search_log_by_session_id(log_path, session_id, limit=100):
    """
    Reads log lines from the log file, parses JSON, and returns logs where session_id matches.
    """
    results = []
    if not os.path.isfile(log_path):
        return results

    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    # Most recent first
    lines = lines[::-1]

    for line in lines:
        json_start = line.find("{")
        if json_start != -1:
            try:
                log_json = json.loads(line[json_start:])
                if log_json.get("session_id") == session_id:
                    results.append(log_json)
                    if len(results) >= limit:
                        break
            except Exception:
                continue
    return results