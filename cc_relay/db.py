import sqlite3
from pathlib import Path

_DEFAULT_DB = Path.home() / ".relay" / "decisions.db"


def _db_path(path: Path | None) -> Path:
    return path if path is not None else _DEFAULT_DB


def init_db(db_path: Path | None = None) -> Path:
    p = _db_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                action_description TEXT NOT NULL,
                decision TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_decisions_type_time ON decisions (action_type, created_at DESC, id DESC)"
        )
        # pending_decisions kept for schema compatibility; no longer written to
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                action_description TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    return p


def record_decision(
    action_type: str,
    action_description: str,
    decision: str,
    risk_level: str,
    db_path: Path | None = None,
) -> None:
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            "INSERT INTO decisions (action_type, action_description, decision, risk_level) VALUES (?, ?, ?, ?)",
            (action_type, action_description, decision, risk_level),
        )


_APPROVAL_RATE_WINDOW = 50  # only consider the most recent N decisions per action type
_HALF_LIFE_DAYS = 7.0  # decisions lose half their weight every 7 days


def _weighted(action_type: str, db_path: Path | None) -> tuple[float, float]:
    """Return (weighted_approved, weighted_total) using exponential time decay."""
    import math
    with sqlite3.connect(_db_path(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT decision,
                   CAST((julianday('now') - julianday(created_at)) AS REAL) AS age_days
            FROM decisions
            WHERE action_type = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (action_type, _APPROVAL_RATE_WINDOW),
        ).fetchall()
    w_total = 0.0
    w_approved = 0.0
    for decision, age_days in rows:
        w = math.pow(0.5, age_days / _HALF_LIFE_DAYS)
        w_total += w
        if decision == "approved":
            w_approved += w
    return w_approved, w_total


def get_approval_rate(action_type: str, db_path: Path | None = None) -> float:
    w_approved, w_total = _weighted(action_type, db_path)
    if not w_total:
        return 0.5
    return w_approved / w_total


def get_count(action_type: str, db_path: Path | None = None) -> float:
    """Return effective sample weight (sum of decayed weights) for the approval-rate window."""
    _, w_total = _weighted(action_type, db_path)
    return w_total


def get_raw_count(action_type: str, db_path: Path | None = None) -> int:
    """Return total number of decisions ever recorded for this action type."""
    with sqlite3.connect(_db_path(db_path)) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE action_type = ?", (action_type,)
        ).fetchone()[0]



def get_stats(db_path: Path | None = None) -> dict:
    """Return approval stats for all action types plus total decision count."""
    with sqlite3.connect(_db_path(db_path)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        action_types = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT action_type FROM decisions ORDER BY action_type"
            ).fetchall()
        ]
    by_type = []
    for at in action_types:
        with sqlite3.connect(_db_path(db_path)) as conn:
            raw_total = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE action_type = ?", (at,)
            ).fetchone()[0]
        w_approved, w_total = _weighted(at, db_path)
        by_type.append({
            "action_type": at,
            "total": raw_total,
            "effective_weight": round(w_total, 2),
            "approval_rate": round(w_approved / w_total, 3) if w_total else 0.5,
        })
    by_type.sort(key=lambda r: r["total"], reverse=True)
    return {"total_decisions": total, "by_action_type": by_type}


def get_recent_decisions(
    action_type: str, limit: int = 20, db_path: Path | None = None
) -> list[dict]:
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT action_type, action_description, decision, risk_level, created_at
            FROM decisions WHERE action_type = ?
            ORDER BY created_at DESC, id DESC LIMIT ?
            """,
            (action_type, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def approve_latest_rejected(
    action_type: str,
    action_description: str,
    db_path: Path | None = None,
) -> None:
    """Flip the most recent rejected decision for this action to approved.

    Called from PostToolUse when the tool actually ran (user approved the ask prompt).
    Falls back to action_type-only match so a stale description never leaves a
    rejected record uncorrected.
    """
    p = _db_path(db_path)
    with sqlite3.connect(p) as conn:
        row = conn.execute(
            """
            SELECT id FROM decisions
            WHERE action_type = ? AND action_description = ? AND decision = 'rejected'
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (action_type, action_description),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT id FROM decisions
                WHERE action_type = ? AND decision = 'rejected'
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (action_type,),
            ).fetchone()
        if row is None:
            return
        conn.execute("UPDATE decisions SET decision = 'approved' WHERE id = ?", (row[0],))


def reset_action_type(action_type: str, db_path: Path | None = None) -> int:
    """Delete all decisions for an action type. Returns count deleted."""
    p = _db_path(db_path)
    with sqlite3.connect(p) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE action_type = ?", (action_type,)
        ).fetchone()
        count = row[0]
        conn.execute("DELETE FROM decisions WHERE action_type = ?", (action_type,))
        return count
