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


def get_approval_rate(action_type: str, db_path: Path | None = None) -> float:
    with sqlite3.connect(_db_path(db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE action_type = ?", (action_type,)
        ).fetchone()
        total = row[0]
        if total == 0:
            return 0.5

        row = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE action_type = ? AND decision = 'approved'",
            (action_type,),
        ).fetchone()
        approved = row[0]
        return approved / total


def get_stats(db_path: Path | None = None) -> dict:
    """Return approval stats for all action types plus total decision count."""
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        rows = conn.execute("""
            SELECT
                action_type,
                COUNT(*) AS total,
                SUM(CASE WHEN decision = 'approved' THEN 1 ELSE 0 END) AS approved
            FROM decisions
            GROUP BY action_type
            ORDER BY total DESC
        """).fetchall()
        by_type = [
            {
                "action_type": r["action_type"],
                "total": r["total"],
                "approved": r["approved"],
                "approval_rate": round(r["approved"] / r["total"], 3),
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
