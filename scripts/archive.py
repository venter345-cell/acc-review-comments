"""Archive review comments posted to ntfy.sh (messages expire there after 12 hours) into this repo.

Every page that collects comments posts JSON events to its ntfy topic. This script polls each topic,
merges new events into <name>.json (deduplicated by ntfy message id) and rewrites <name>.md for reading.
"""
import base64, json, os, time, urllib.request
from datetime import datetime, timezone, timedelta

TOPICS = {"clinotrend-gbp": "acc-clinotrend-gbp-591837a28a"}
SAST = timezone(timedelta(hours=2))

def poll(topic):
    url = f"https://ntfy.sh/{topic}/json?poll=1&since=all"
    with urllib.request.urlopen(url, timeout=30) as r:
        lines = r.read().decode("utf-8").splitlines()
    out = []
    for line in lines:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("event") != "message":
            continue
        body = None
        for t in m.get("tags", []) or []:
            if t.startswith("ev:"):
                try:
                    raw = t[3:] + "=" * (-len(t[3:]) % 4)
                    body = json.loads(base64.urlsafe_b64decode(raw).decode("utf-8"))
                except Exception:
                    body = None
        if body is None:
            body = {"type": "comment", "id": m["id"]}
        if body.get("type", "comment") == "comment":
            body["text"] = m.get("message", "")
        if not isinstance(body, dict):
            continue
        body["_ntfy"] = m["id"]
        body["_time"] = m.get("time")
        out.append(body)
    return out

def resolve(events):
    comments, deleted = {}, set()
    for e in sorted(events, key=lambda x: x.get("_time") or 0):
        if e.get("type") == "delete":
            deleted.add(e.get("id"))
        elif e.get("type", "comment") == "comment" and e.get("id"):
            comments[e["id"]] = e
    return [c for k, c in comments.items() if k not in deleted]

for name, topic in TOPICS.items():
    path = f"{name}.json"
    data = {"topic": topic, "events": []}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    seen = {e.get("_ntfy") for e in data["events"]}
    new = [e for e in poll(topic) if e["_ntfy"] not in seen]
    if not new:
        print(name, "no new events")
        continue
    data["events"].extend(new)
    data["updated"] = int(time.time())
    with open(path, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    live = sorted(resolve(data["events"]), key=lambda c: c.get("_time") or 0)
    md = [f"# Comments: {name}", "", f"Updated {datetime.now(SAST):%d %b %Y %H:%M} SAST. {len(live)} open comments.", ""]
    for i, c in enumerate(live, 1):
        when = datetime.fromtimestamp(c.get("_time") or 0, SAST).strftime("%d %b %Y %H:%M")
        md.append(f"## {i}. {c.get('author') or 'Anonymous'}, {when} SAST")
        md.append(f"Where: {c.get('where') or 'page'}")
        md.append("")
        md.append(str(c.get("text", "")).strip())
        md.append("")
    with open(f"{name}.md", "w") as f:
        f.write("\n".join(md))
    print(name, len(new), "new events")
