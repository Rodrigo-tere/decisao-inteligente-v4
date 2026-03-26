import hashlib
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "decisao_inteligente_v5.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000
    ).hex()


def _build_password_hash(password: str) -> str:
    salt = os.urandom(16).hex()
    return f"{salt}${_hash_password(password, salt)}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if "$" in stored:
        salt, hashed = stored.split("$", 1)
        return _hash_password(password, salt) == hashed
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            decision_text TEXT NOT NULL,
            score REAL NOT NULL,
            recommendation TEXT NOT NULL,
            inputs_json TEXT,
            penalties_json TEXT,
            notes TEXT,
            tags TEXT,
            review_due_at TEXT,
            outcome_status TEXT,
            outcome_quality INTEGER,
            outcome_notes TEXT,
            confidence_user REAL,
            confidence_system REAL,
            confidence_gap REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()


def migrate_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(decisions)")
    cols = [row["name"] for row in cur.fetchall()]
    new_cols = {
        "tags": "TEXT",
        "review_due_at": "TEXT",
        "confidence_user": "REAL",
        "confidence_system": "REAL",
        "confidence_gap": "REAL",
    }
    for col, col_type in new_cols.items():
        if col not in cols:
            cur.execute(f"ALTER TABLE decisions ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()


def seed_default_user():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("admin", _build_password_hash("admin123"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    conn.close()


def create_user(username: str, password: str) -> Tuple[bool, str]:
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return False, "Preencha usuário e senha."
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, _build_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError:
        return False, "Esse usuário já existe."
    except Exception as e:
        return False, f"Erro ao criar usuário: {e}"


def verify_login(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    if _verify_password(password, data["password_hash"]):
        return data
    return None


def update_password(username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
    user = verify_login(username, current_password)
    if not user:
        return False, "Senha atual incorreta."
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (_build_password_hash(new_password.strip()), username),
    )
    conn.commit()
    conn.close()
    return True, "Senha atualizada com sucesso."


def insert_decision(
    user_id: int,
    mode: str,
    title: str,
    category: str,
    decision_text: str,
    score: float,
    recommendation: str,
    inputs: Dict[str, Any],
    penalties: List[str],
    notes: str,
    tags: str,
    review_due_at: Optional[str],
    confidence_user: Optional[float] = None,
    confidence_system: Optional[float] = None,
    confidence_gap: Optional[float] = None,
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO decisions (
            user_id, mode, title, category, decision_text, score, recommendation,
            inputs_json, penalties_json, notes, tags, review_due_at,
            confidence_user, confidence_system, confidence_gap, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            mode,
            title,
            category,
            decision_text,
            float(score),
            recommendation,
            json.dumps(inputs, ensure_ascii=False),
            json.dumps(penalties, ensure_ascii=False),
            notes,
            tags,
            review_due_at,
            confidence_user,
            confidence_system,
            confidence_gap,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    decision_id = cur.lastrowid
    conn.close()
    return int(decision_id)


def list_decisions_df(user_id: int):
    import pandas as pd

    conn = get_conn()
    query = """
        SELECT
            id, created_at, mode, title, category, decision_text, score, recommendation,
            tags, confidence_user, confidence_system, confidence_gap,
            review_due_at, outcome_status, outcome_quality
        FROM decisions
        WHERE user_id = ?
        ORDER BY id DESC
    """
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df


def export_decisions_df(user_id: int):
    import pandas as pd

    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM decisions WHERE user_id = ? ORDER BY id DESC", conn, params=(user_id,)
    )
    conn.close()
    return df


def get_decision(decision_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["inputs"] = json.loads(data["inputs_json"]) if data.get("inputs_json") else {}
    data["penalties"] = json.loads(data["penalties_json"]) if data.get("penalties_json") else []
    return data


def update_outcome(decision_id: int, status: str, quality: Optional[int], notes: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE decisions SET outcome_status = ?, outcome_quality = ?, outcome_notes = ? WHERE id = ?",
        (status, quality, notes, decision_id),
    )
    conn.commit()
    conn.close()


def get_summary_stats(user_id: int) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total, AVG(score) AS avg_score FROM decisions WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    total = row["total"] or 0
    avg_score = float(row["avg_score"] or 0)

    cur.execute(
        "SELECT COUNT(*) AS reviewed, AVG(outcome_quality) AS avg_quality FROM decisions WHERE user_id = ? AND outcome_quality IS NOT NULL",
        (user_id,),
    )
    row = cur.fetchone()
    reviewed = row["reviewed"] or 0
    avg_quality = float(row["avg_quality"] or 0)
    conn.close()
    return {
        "total": total,
        "avg_score": avg_score,
        "reviewed": reviewed,
        "avg_quality": avg_quality,
    }


def get_monthly_summary(user_id: int):
    import pandas as pd

    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT substr(created_at, 1, 7) AS ano_mes, COUNT(*) AS quantidade
        FROM decisions
        WHERE user_id = ?
        GROUP BY substr(created_at, 1, 7)
        ORDER BY ano_mes
        """,
        conn,
        params=(user_id,),
    )
    conn.close()
    return df


def get_recommendation_breakdown(user_id: int):
    import pandas as pd

    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT recommendation, COUNT(*) AS total
        FROM decisions
        WHERE user_id = ?
        GROUP BY recommendation
        ORDER BY total DESC, recommendation ASC
        """,
        conn,
        params=(user_id,),
    )
    conn.close()
    return df


def get_category_quality_summary(user_id: int):
    import pandas as pd

    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT category, COUNT(*) AS total, AVG(outcome_quality) AS avg_quality
        FROM decisions
        WHERE user_id = ? AND outcome_quality IS NOT NULL
        GROUP BY category
        ORDER BY avg_quality DESC, total DESC
        """,
        conn,
        params=(user_id,),
    )
    conn.close()
    return df


def get_confidence_gap_summary(user_id: int) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            AVG(ABS(COALESCE(confidence_gap, 0))) AS avg_gap_abs,
            SUM(CASE WHEN confidence_gap >= 2 THEN 1 ELSE 0 END) AS overconfident_count,
            SUM(CASE WHEN confidence_gap <= -2 THEN 1 ELSE 0 END) AS underconfident_count,
            SUM(CASE WHEN confidence_gap > -2 AND confidence_gap < 2 THEN 1 ELSE 0 END) AS calibrated_count
        FROM decisions
        WHERE user_id = ? AND confidence_gap IS NOT NULL
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    return {
        "avg_gap_abs": float((row["avg_gap_abs"] or 0) if row else 0),
        "overconfident_count": int((row["overconfident_count"] or 0) if row else 0),
        "underconfident_count": int((row["underconfident_count"] or 0) if row else 0),
        "calibrated_count": int((row["calibrated_count"] or 0) if row else 0),
    }


def get_pattern_summary(user_id: int) -> Dict[str, str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT category, COUNT(*) AS c FROM decisions
        WHERE user_id = ?
        GROUP BY category
        ORDER BY c DESC, category ASC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cur.fetchone()
    top_category = row["category"] if row else "-"

    cur.execute(
        """
        SELECT mode, COUNT(*) AS c FROM decisions
        WHERE user_id = ?
        GROUP BY mode
        ORDER BY c DESC, mode ASC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cur.fetchone()
    top_mode = row["mode"] if row else "-"

    cur.execute("SELECT penalties_json FROM decisions WHERE user_id = ? AND penalties_json IS NOT NULL", (user_id,))
    rows = cur.fetchall()
    penalty_counts: Dict[str, int] = {}
    for r in rows:
        try:
            items = json.loads(r["penalties_json"])
            for item in items:
                penalty_counts[item] = penalty_counts.get(item, 0) + 1
        except Exception:
            pass
    top_penalty = "-"
    if penalty_counts:
        top_penalty = sorted(penalty_counts.items(), key=lambda x: (-x[1], x[0]))[0][0]
    conn.close()
    return {"top_category": top_category, "top_mode": top_mode, "top_penalty": top_penalty}


def get_bias_breakdown(user_id: int):
    import pandas as pd

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT inputs_json FROM decisions WHERE user_id = ? AND inputs_json IS NOT NULL", (user_id,))
    rows = cur.fetchall()
    conn.close()

    counters = {
        "Viés de confirmação": 0,
        "Efeito manada": 0,
        "Aversão à perda": 0,
        "Ego/excesso de confiança": 0,
        "Ancoragem": 0,
        "Alerta de viés (rápido)": 0,
    }
    for row in rows:
        try:
            data = json.loads(row["inputs_json"])
        except Exception:
            data = {}
        if data.get("bias_confirmation"):
            counters["Viés de confirmação"] += 1
        if data.get("bias_herd"):
            counters["Efeito manada"] += 1
        if data.get("bias_loss"):
            counters["Aversão à perda"] += 1
        if data.get("bias_ego"):
            counters["Ego/excesso de confiança"] += 1
        if data.get("bias_anchor"):
            counters["Ancoragem"] += 1
        if data.get("bias_alert") == "Sim":
            counters["Alerta de viés (rápido)"] += 1

    records = [{"bias_name": k, "total": v} for k, v in counters.items() if v > 0]
    if not records:
        return pd.DataFrame(columns=["bias_name", "total"])
    return pd.DataFrame(records).sort_values(["total", "bias_name"], ascending=[False, True])
