"""The public board's payload (docs/public-board.md): tonight's event, nothing else.

`build` copies named fields out of the operations document into new dicts and
never passes a document object through whole, so a field added to the document
later stays private until someone adds it here on purpose. Left out by
construction: every internal id (the board has slot ids made from bracket
positions), notes, the audit log (read only for when a live match went on its
table), sources, the regulars roster (read only for the current names of
tonight's entrants), ratings, faces, guest flags, absences, archived nights and
every setting but the on/off switch.
"""
import hashlib
import json
from datetime import datetime, timezone

# The words a match may carry, from the module that writes them: the board keeps
# no list of its own to fall behind (R36/C3).
from annotator.operations import MATCH_RESULTS, MATCH_STATUSES

OFF = {"board": "off"}


def build(state):
    """The board for the operations document `state` (as Store.get returns it)."""
    if (state.get("settings") or {}).get("publicBoard") is False:
        return dict(OFF)
    t = state["tournament"]
    roster = {p["id"]: p["name"] for p in state.get("players", [])}
    # An entrant as the console names it (ops.js ename): each member's current
    # roster name, else the name they registered under. Where the console has no
    # name at all it fills the hole with a word of its own (ops.js t('unknown'));
    # this payload carries no words, so a member with no name adds nothing here.
    names = {e["id"]: " / ".join(roster.get(m.get("pid")) or m.get("name") or "" for m in e["members"])
             for e in t["entrants"]}
    slots, in_round = {}, {}
    for m in t["matches"]:
        in_round[m["round"]] = in_round.get(m["round"], 0) + 1
        slots[m["id"]] = f"r{m['round']}m{in_round[m['round']]}"
    # Matches carry no start time; the latest match_schedule event for one is when it went on its table.
    since = {(e.get("context") or {}).get("id"): e.get("createdAt")
             for e in state.get("events", []) if e.get("action") == "match_schedule"}

    def side(m, index):
        """A side as the console names it, a bye, or the board's own word-free marker.

        ops.js sideName (annotator/ops.js:853) hands a side no entrant holds to ename,
        which answers with a word from the console's table in the console's language
        (t('pending')). This payload carries no words - annotator/board.js owns the
        board's, and its tbd is "To be decided"/"待定" - so a side the board cannot name
        is marked, never given a word of its own. A side it can name carries the name the
        console gives it, the empty one included: only the word is out of reach.
        """
        entrant = m["sides"][index]
        if entrant:
            return {"name": names[entrant]} if entrant in names else {"tbd": True}
        return {"bye": True} if m.get("result") == "bye" else {"tbd": True}

    def match(m):
        item = {"slot": slots[m["id"]], "round": m["round"], "sides": [side(m, 0), side(m, 1)],
                "score": [int(m["score"][0]), int(m["score"][1])],
                "status": m["status"] if m["status"] in MATCH_STATUSES else "pending",
                "winner": m["sides"].index(m["winnerId"]) if m.get("winnerId") in m["sides"] and m.get("winnerId") else None}
        if m.get("result") in MATCH_RESULTS:
            item["result"] = m["result"]
        if m["status"] == "live":
            item.update(table=int(m["table"]), since=since.get(m["id"]))
        return item

    def signed(m):  # ops.js signedResult: a played or forfeited result between two entrants
        return m["status"] == "complete" and m.get("result") != "bye" and all(m["sides"])

    standings = []
    for e in t["entrants"]:
        games = [m for m in t["matches"] if signed(m) and e["id"] in m["sides"]]
        won = sum(1 for m in games if m["winnerId"] == e["id"])
        standings.append({"name": names[e["id"]], "won": won, "lost": len(games) - won, "played": len(games)})
    # The table's order: wins, then win rate (unplayed last), then name. The console
    # ordered entrants this way when it kept an event table (ops.js eventTable:
    # b.wins-a.wins || win rate || a.name.localeCompare(b.name)); 2f6eb14 deleted that
    # function, and the console now shows each entrant's record on their own row, in
    # registration order. So this order is the board's own - its name tie-break is
    # casefold, not localeCompare - and tests/test_board_api.py pins the order and
    # compares the numbers sorted here field by field with the console's record().
    standings.sort(key=lambda r: (-r["won"], -(r["won"] / r["played"] if r["played"] else -1), r["name"].casefold()))

    rounds = {}
    for m in t["matches"]:
        rounds.setdefault(m["round"], []).append(match(m))
    return {
        "board": "on",
        "revision": state["revision"],
        "event": {"name": t.get("name") or "", "format": t["format"], "race_to": t["raceTo"], "phase": t["status"]},
        "tables": [match(m) for m in sorted((m for m in t["matches"] if m["status"] == "live"),
                                            key=lambda m: m["table"])],
        # Ready matches first, then those held for a missing player; bracket order within each.
        "next": [match(m) for m in sorted((m for m in t["matches"] if m["status"] in ("scheduled", "delayed")),
                                          key=lambda m: (m["status"] == "delayed", m["round"]))],
        "bracket": [{"round": number, "matches": items} for number, items in sorted(rounds.items())],
        "standings": standings,
    }


def encode(board, now=None):
    """(etag, body). The weak ETag is the revision and a digest of everything but
    served_at, so it changes exactly when what the board shows does."""
    stable = json.dumps(board, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    etag = 'W/"%s-%s"' % (board.get("revision", "off"), hashlib.sha256(stable.encode()).hexdigest()[:16])
    if board.get("board") == "on":
        board = dict(board, served_at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"))
    return etag, json.dumps(board, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
