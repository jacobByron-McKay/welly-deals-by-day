"""Merge the per-agent contact sweep files into woap_outreach.json and generate the
per-venue outreach messages.

The message body is Jacob's own wording, used verbatim apart from three fixes he would
obviously make himself before sending to 244 businesses:
  "Ive"     -> "I've"
  "offical" -> "official"
  "welly on a plate" -> "Welly on a Plate"   (proper noun)
Nothing else is reworded. Do not "improve" this copy — it is deliberately plain so it
reads like one person typing it once, not like marketing.

Usage:
  python tools/woap_outreach_build.py merge     # pull agent files into woap_outreach.json
  python tools/woap_outreach_build.py messages  # write woap_messages.json (ready to send)
  python tools/woap_outreach_build.py status    # coverage report
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = (r"C:\Users\byron\AppData\Local\Temp\claude"
           r"\D--claude-Projects-Auckland-deals-welly-deals-by-day"
           r"\2f66bae4-a740-4ef5-90de-373bc357cd08\scratchpad")
OUTREACH = os.path.join(BASE, "woap_outreach.json")
BURGERS = os.path.join(BASE, "woap_burgers.json")
MESSAGES = os.path.join(BASE, "woap_messages.json")

LEADERBOARD_URL = "https://welly-deals-by-day.co.nz/?burgers=1"

SUBJECT = "Quick question about your burger pic"

BODY = """Heya,

I run a live burger leaderboard for Welly on a Plate burgers. I was wondering if you'd \
mind if I please used a pic of your burger ({burger}) on there, it looks delicious! I've \
got the one you submitted for the official WOAP if that's ok, just thought I'd check. \
Happy to update it, or drop it if need be.

Kindest regards
Jacob Byron-McKay

{link}"""

# Plural variant, used only when one contact covers more than one burger (e.g. two branches
# of the same business sharing an inbox). Same voice, just agreeing in number.
BODY_PLURAL = """Heya,

I run a live burger leaderboard for Welly on a Plate burgers. I was wondering if you'd \
mind if I please used pics of your burgers ({burger}) on there, they look delicious! I've \
got the ones you submitted for the official WOAP if that's ok, just thought I'd check. \
Happy to update them, or drop them if need be.

Kindest regards
Jacob Byron-McKay

{link}"""

# Instagram and Facebook DMs need to be one block — a multi-paragraph DM reads badly and
# the composers submit on Enter.
DM = ("Heya, I run a live burger leaderboard for Welly on a Plate burgers. I was wondering "
      "if you'd mind if I please used a pic of your burger ({burger}) on there, it looks "
      "delicious! I've got the one you submitted for the official WOAP if that's ok, just "
      "thought I'd check. Happy to update it, or drop it if need be. Kindest regards, "
      "Jacob Byron-McKay {link}")

DM_PLURAL = ("Heya, I run a live burger leaderboard for Welly on a Plate burgers. I was wondering "
             "if you'd mind if I please used pics of your burgers ({burger}) on there, they look "
             "delicious! I've got the ones you submitted for the official WOAP if that's ok, just "
             "thought I'd check. Happy to update them, or drop them if need be. Kindest regards, "
             "Jacob Byron-McKay {link}")


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)


def merge():
    rows = load(OUTREACH)
    # Trailing letter allows re-run files (emails_189_203b.json) from resumed sweeps.
    files = [f for f in os.listdir(SCRATCH) if re.match(r"emails_\d+_\d+[a-z]?\.json$", f)]
    applied = 0
    for fn in sorted(files):
        try:
            chunk = load(os.path.join(SCRATCH, fn))
        except Exception as e:
            print("SKIP %s (%s)" % (fn, e))
            continue
        for r in chunk:
            i = r.get("index")
            if i is None or not (0 <= i < len(rows)):
                print("SKIP bad index %r in %s" % (i, fn))
                continue
            ch, val = r.get("channel"), r.get("value")
            # Guard: a channel of "email" whose value is not an address is a bad row.
            if ch == "email" and (not val or "@" not in val):
                print("SKIP malformed email row idx=%s in %s" % (i, fn))
                continue
            rows[i]["channel"] = ch
            rows[i]["contact"] = val
            rows[i]["evidence"] = r.get("evidence")
            rows[i]["contact_confidence"] = r.get("confidence")
            applied += 1
    save(OUTREACH, rows)
    print("merged %d files, applied %d rows" % (len(files), applied))


def messages():
    """Build one message PER CONTACT, not per burger.

    Two things this has to get right:
      * A contact shared by two branches (Puku Pies Lyall Bay + Johnsonville share
        info@pukupies.co.nz) must get ONE message naming both burgers. Two near-identical
        emails landing in the same inbox minutes apart reads as spam.
      * Low-confidence contacts are NOT auto-sent. They are written to a separate
        review list for Jacob to eyeball, because a wrong address is worse than none.
    """
    rows = load(OUTREACH)
    burgers = load(BURGERS)
    by_venue = {}
    for b in burgers:
        by_venue.setdefault(b["venue"], b)

    groups, review = {}, []
    for i, r in enumerate(rows):
        ch = r.get("channel")
        # Rows carried over from the first pilot use "email"/"email_confidence".
        if not ch and r.get("email"):
            ch, r["contact"] = "email", r["email"]
        if ch not in ("email", "facebook", "instagram"):
            continue
        contact = r.get("contact")
        if not contact:
            continue
        burger = r.get("burger") or (by_venue.get(r["venue"], {}) or {}).get("name")
        if not burger:
            print("SKIP idx=%d %s: no burger name" % (i, r["venue"]))
            continue
        conf = r.get("contact_confidence") or r.get("email_confidence")
        entry = {"index": i, "venue": r["venue"], "burger": burger,
                 "channel": ch, "contact": contact, "confidence": conf,
                 "evidence": r.get("evidence")}
        if conf and conf.lower() != "high":
            review.append(entry)
            continue
        key = (ch, contact.lower())
        groups.setdefault(key, []).append(entry)

    out = []
    for (ch, contact), items in groups.items():
        names = [it["burger"] for it in items]
        # "X" / "X and Y" / "X, Y and Z" — never a bare comma list ending flat.
        if len(names) == 1:
            burger_str = names[0]
        elif len(names) == 2:
            burger_str = "%s and %s" % (names[0], names[1])
        else:
            burger_str = "%s and %s" % (", ".join(names[:-1]), names[-1])
        rec = {
            "venues": [it["venue"] for it in items],
            "indices": [it["index"] for it in items],
            "burger": burger_str,
            "channel": ch,
            "contact": items[0]["contact"],
            "sent": False,
        }
        multi = len(names) > 1
        if ch == "email":
            rec["subject"] = SUBJECT
            tpl = BODY_PLURAL if multi else BODY
        else:
            tpl = DM_PLURAL if multi else DM
        rec["body"] = tpl.format(burger=burger_str, link=LEADERBOARD_URL)
        out.append(rec)

    out.sort(key=lambda m: (m["channel"], m["contact"]))
    save(MESSAGES, out)
    save(os.path.join(BASE, "woap_needs_review.json"), review)
    counts = {}
    for m in out:
        counts[m["channel"]] = counts.get(m["channel"], 0) + 1
    print("wrote %d messages: %s" % (len(out), counts))
    print("held for manual review (low confidence): %d" % len(review))
    merged = [m for m in out if len(m["indices"]) > 1]
    for m in merged:
        print("  merged into one message: %s -> %s" % (m["contact"], m["venues"]))


def status():
    rows = load(OUTREACH)
    done = [r for r in rows if r.get("channel") or r.get("email")]
    counts = {}
    for r in rows:
        ch = r.get("channel") or ("email" if r.get("email") else None)
        counts[ch] = counts.get(ch, 0) + 1
    print("total %d | resolved %d | remaining %d" % (len(rows), len(done), len(rows) - len(done)))
    print("by channel:", counts)
    missing = [i for i, r in enumerate(rows) if not (r.get("channel") or r.get("email"))]
    if missing:
        print("unresolved indices:", missing[:60], "..." if len(missing) > 60 else "")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"merge": merge, "messages": messages, "status": status}[cmd]()
