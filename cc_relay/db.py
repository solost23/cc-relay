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


def get_approval_rate(action_type: str, db_path: Path | None = None) -> float:
    with sqlite3.connect(_db_path(db_path)) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN decision = 'approved' THEN 1 ELSE 0 END) AS approved
            FROM (
                SELECT decision FROM decisions
                WHERE action_type = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            )
            """,
            (action_type, _APPROVAL_RATE_WINDOW),
        ).fetchone()
        total, approved = row
        if not total:
            return 0.5
        return approved / total


def get_count(action_type: str, db_path: Path | None = None) -> int:
    with sqlite3.connect(_db_path(db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE action_type = ?",
            (action_type,),
        ).fetchone()
        return row[0]


def get_stats(db_path: Path | None = None) -> dict:
    """Return approval stats for all action types plus total decision count."""
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        rows = conn.execute(
            """
            SELECT
                action_type,
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN rn <= ? AND decision = 'approved' THEN 1 ELSE 0 END), 0) AS window_approved,
                SUM(CASE WHEN rn <= ? THEN 1 ELSE 0 END) AS window_total
            FROM (
                SELECT action_type, decision,
                       ROW_NUMBER() OVER (PARTITION BY action_type ORDER BY created_at DESC, id DESC) AS rn
                FROM decisions
            )
            GROUP BY action_type
            ORDER BY total DESC
            """,
            (_APPROVAL_RATE_WINDOW, _APPROVAL_RATE_WINDOW),
        ).fetchall()
        by_type = [
            {
                "action_type": r["action_type"],
                "total": r["total"],
                "window_total": r["window_total"],
                "window_approved": r["window_approved"],
                "approval_rate": round(r["window_approved"] / r["window_total"], 3) if r["window_total"] else 0.5,
            }
            for r in rows
        ]
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
