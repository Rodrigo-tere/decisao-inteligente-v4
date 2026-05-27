
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import streamlit as st
except Exception:
    st = None

try:
    from supabase import create_client
except Exception:
    create_client = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_SQLITE_DB_PATH = os.path.join(BASE_DIR, "decisao_inteligente_cloud_local.db")

def _default_sqlite_path() -> str:
    configured = os.environ.get("DECISAO_SQLITE_PATH")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    local_base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local_base, "DecisaoInteligente", "decisao_inteligente_cloud_local.db")

SQLITE_DB_PATH = _default_sqlite_path()

def _ensure_sqlite_parent_dir() -> None:
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)

def _bootstrap_sqlite_file() -> None:
    _ensure_sqlite_parent_dir()
    if os.path.exists(SQLITE_DB_PATH) or not os.path.exists(BUNDLED_SQLITE_DB_PATH):
        return
    try:
        shutil.copy2(BUNDLED_SQLITE_DB_PATH, SQLITE_DB_PATH)
    except Exception:
        pass

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000).hex()

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

def _get_supabase_client():
    if create_client is None:
        return None
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if st is not None:
        try:
            url = url or st.secrets["SUPABASE_URL"]
            key = key or st.secrets["SUPABASE_KEY"]
        except Exception:
            pass
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

def using_supabase() -> bool:
    return _get_supabase_client() is not None

def get_conn():
    _bootstrap_sqlite_file()
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _sqlite_init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
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
    """)
    conn.commit()
    conn.close()

def _sqlite_seed_default_user():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)", ("admin", _build_password_hash("admin123"), _now()))
        conn.commit()
    conn.close()

def _sqlite_create_user(username: str, password: str) -> Tuple[bool, str]:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)", (username.strip(), _build_password_hash(password.strip()), _now()))
        conn.commit()
        conn.close()
        return True, "Usuário criado com sucesso."
    except sqlite3.IntegrityError:
        return False, "Esse usuário já existe."
    except Exception as e:
        return False, f"Erro ao criar usuário: {e}"

def _sqlite_verify_login(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row and _verify_password(password, row["password_hash"]):
        return dict(row)
    return None

def _sqlite_update_password(username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
    user = _sqlite_verify_login(username, current_password)
    if not user:
        return False, "Senha atual incorreta."
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = ? WHERE username = ?", (_build_password_hash(new_password.strip()), username))
    conn.commit()
    conn.close()
    return True, "Senha atualizada com sucesso."

def _supabase_seed_default_user():
    sb = _get_supabase_client()
    if sb is None:
        return
    try:
        rows = sb.table("users").select("id").eq("username", "admin").limit(1).execute().data or []
        if not rows:
            sb.table("users").insert({"username": "admin", "password_hash": _build_password_hash("admin123"), "created_at": _now()}).execute()
    except Exception:
        pass

def _supabase_create_user(username: str, password: str) -> Tuple[bool, str]:
    sb = _get_supabase_client()
    try:
        rows = sb.table("users").select("id").eq("username", username.strip()).limit(1).execute().data or []
        if rows:
            return False, "Esse usuário já existe."
        sb.table("users").insert({"username": username.strip(), "password_hash": _build_password_hash(password.strip()), "created_at": _now()}).execute()
        return True, "Usuário criado com sucesso."
    except Exception as e:
        return False, f"Erro ao criar usuário: {e}"

def _supabase_verify_login(username: str, password: str) -> Optional[Dict[str, Any]]:
    sb = _get_supabase_client()
    try:
        rows = sb.table("users").select("*").eq("username", username).limit(1).execute().data or []
        if not rows:
            return None
        row = rows[0]
        if _verify_password(password, row["password_hash"]):
            return row
        return None
    except Exception:
        return None

def _supabase_update_password(username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
    user = _supabase_verify_login(username, current_password)
    if not user:
        return False, "Senha atual incorreta."
    sb = _get_supabase_client()
    try:
        sb.table("users").update({"password_hash": _build_password_hash(new_password.strip())}).eq("username", username).execute()
        return True, "Senha atualizada com sucesso."
    except Exception as e:
        return False, f"Erro ao atualizar senha: {e}"

def init_db():
    if not using_supabase():
        _sqlite_init_db()

def migrate_db():
    if not using_supabase():
        _sqlite_init_db()

def seed_default_user():
    if using_supabase():
        _supabase_seed_default_user()
    else:
        _sqlite_seed_default_user()

def create_user(username: str, password: str) -> Tuple[bool, str]:
    return _supabase_create_user(username, password) if using_supabase() else _sqlite_create_user(username, password)

def verify_login(username: str, password: str) -> Optional[Dict[str, Any]]:
    return _supabase_verify_login(username, password) if using_supabase() else _sqlite_verify_login(username, password)

def update_password(username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
    return _supabase_update_password(username, current_password, new_password) if using_supabase() else _sqlite_update_password(username, current_password, new_password)

def insert_decision(user_id: int, mode: str, title: str, category: str, decision_text: str, score: float, recommendation: str,
                    inputs: Dict[str, Any], penalties: List[str], notes: str, tags: str, review_due_at: Optional[str],
                    confidence_user: Optional[float] = None, confidence_system: Optional[float] = None,
                    confidence_gap: Optional[float] = None) -> int:
    if using_supabase():
        sb = _get_supabase_client()
        rows = sb.table("decisions").insert({
            "user_id": user_id, "mode": mode, "title": title, "category": category, "decision_text": decision_text,
            "score": float(score), "recommendation": recommendation, "inputs_json": json.dumps(inputs, ensure_ascii=False),
            "penalties_json": json.dumps(penalties, ensure_ascii=False), "notes": notes, "tags": tags,
            "review_due_at": review_due_at, "confidence_user": confidence_user, "confidence_system": confidence_system,
            "confidence_gap": confidence_gap, "created_at": _now()
        }).execute().data or []
        return int(rows[0]["id"]) if rows else 0

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO decisions (
        user_id, mode, title, category, decision_text, score, recommendation,
        inputs_json, penalties_json, notes, tags, review_due_at,
        confidence_user, confidence_system, confidence_gap, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, mode, title, category, decision_text, float(score), recommendation,
        json.dumps(inputs, ensure_ascii=False), json.dumps(penalties, ensure_ascii=False), notes, tags,
        review_due_at, confidence_user, confidence_system, confidence_gap, _now()
    ))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def list_decisions_df(user_id: int):
    import pandas as pd
    if using_supabase():
        rows = _get_supabase_client().table("decisions").select("id,created_at,mode,title,category,decision_text,score,recommendation,tags,confidence_user,confidence_system,confidence_gap,review_due_at,outcome_status,outcome_quality").eq("user_id", user_id).order("id", desc=True).execute().data or []
        return pd.DataFrame(rows)
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, created_at, mode, title, category, decision_text, score, recommendation, tags, confidence_user, confidence_system, confidence_gap, review_due_at, outcome_status, outcome_quality FROM decisions WHERE user_id = ? ORDER BY id DESC", conn, params=(user_id,))
    conn.close()
    return df

def export_decisions_df(user_id: int):
    import pandas as pd
    if using_supabase():
        rows = _get_supabase_client().table("decisions").select("*").eq("user_id", user_id).order("id", desc=True).execute().data or []
        return pd.DataFrame(rows)
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM decisions WHERE user_id = ? ORDER BY id DESC", conn, params=(user_id,))
    conn.close()
    return df

def get_decision(decision_id: int) -> Optional[Dict[str, Any]]:
    if using_supabase():
        rows = _get_supabase_client().table("decisions").select("*").eq("id", decision_id).limit(1).execute().data or []
        if not rows:
            return None
        data = rows[0]
        data["inputs"] = json.loads(data["inputs_json"]) if data.get("inputs_json") else {}
        data["penalties"] = json.loads(data["penalties_json"]) if data.get("penalties_json") else []
        return data
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["inputs"] = json.loads(data["inputs_json"]) if data["inputs_json"] else {}
    data["penalties"] = json.loads(data["penalties_json"]) if data["penalties_json"] else []
    return data

def update_outcome(decision_id: int, status: str, quality: Optional[int], notes: str):
    if using_supabase():
        _get_supabase_client().table("decisions").update({"outcome_status": status, "outcome_quality": quality, "outcome_notes": notes}).eq("id", decision_id).execute()
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE decisions SET outcome_status = ?, outcome_quality = ?, outcome_notes = ? WHERE id = ?", (status, quality, notes, decision_id))
    conn.commit()
    conn.close()

def get_summary_stats(user_id: int) -> Dict[str, Any]:
    df = export_decisions_df(user_id)
    if df.empty:
        return {"total": 0, "avg_score": 0.0, "reviewed": 0, "avg_quality": 0.0}
    reviewed = int(df["outcome_quality"].notna().sum()) if "outcome_quality" in df.columns else 0
    avg_quality = float(df["outcome_quality"].dropna().astype(float).mean()) if reviewed else 0.0
    avg_score = float(df["score"].astype(float).mean()) if "score" in df.columns else 0.0
    return {"total": int(len(df)), "avg_score": avg_score, "reviewed": reviewed, "avg_quality": avg_quality}

def get_monthly_summary(user_id: int):
    import pandas as pd
    df = export_decisions_df(user_id)
    if df.empty:
        return pd.DataFrame(columns=["ano_mes", "quantidade"])
    df["ano_mes"] = df["created_at"].astype(str).str.slice(0, 7)
    return df.groupby("ano_mes").size().reset_index(name="quantidade").sort_values("ano_mes")

def get_recommendation_breakdown(user_id: int):
    import pandas as pd
    df = export_decisions_df(user_id)
    if df.empty or "recommendation" not in df.columns:
        return pd.DataFrame(columns=["recommendation", "total"])
    return df.groupby("recommendation").size().reset_index(name="total").sort_values(["total","recommendation"], ascending=[False, True])

def get_category_quality_summary(user_id: int):
    import pandas as pd
    df = export_decisions_df(user_id)
    if df.empty or "outcome_quality" not in df.columns:
        return pd.DataFrame(columns=["category","total","avg_quality"])
    df = df[df["outcome_quality"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=["category","total","avg_quality"])
    df["outcome_quality"] = df["outcome_quality"].astype(float)
    out = df.groupby("category").agg(total=("category","size"), avg_quality=("outcome_quality","mean")).reset_index()
    return out.sort_values(["avg_quality","total"], ascending=[False, False])

def get_confidence_gap_summary(user_id: int) -> Dict[str, Any]:
    df = export_decisions_df(user_id)
    if df.empty or "confidence_gap" not in df.columns:
        return {"avg_gap_abs":0.0,"overconfident_count":0,"underconfident_count":0,"calibrated_count":0}
    df = df[df["confidence_gap"].notna()].copy()
    if df.empty:
        return {"avg_gap_abs":0.0,"overconfident_count":0,"underconfident_count":0,"calibrated_count":0}
    df["confidence_gap"] = df["confidence_gap"].astype(float)
    return {
        "avg_gap_abs": float(df["confidence_gap"].abs().mean()),
        "overconfident_count": int((df["confidence_gap"] >= 2).sum()),
        "underconfident_count": int((df["confidence_gap"] <= -2).sum()),
        "calibrated_count": int(((df["confidence_gap"] > -2) & (df["confidence_gap"] < 2)).sum()),
    }

def get_pattern_summary(user_id: int) -> Dict[str, str]:
    df = export_decisions_df(user_id)
    if df.empty:
        return {"top_category":"-","top_mode":"-","top_penalty":"-"}
    top_category = df["category"].value_counts().index[0] if "category" in df.columns and not df["category"].empty else "-"
    top_mode = df["mode"].value_counts().index[0] if "mode" in df.columns and not df["mode"].empty else "-"
    penalty_counts = {}
    if "penalties_json" in df.columns:
        for raw in df["penalties_json"].dropna().tolist():
            try:
                items = json.loads(raw)
                for item in items:
                    penalty_counts[item] = penalty_counts.get(item, 0) + 1
            except Exception:
                pass
    top_penalty = sorted(penalty_counts.items(), key=lambda x: (-x[1], x[0]))[0][0] if penalty_counts else "-"
    return {"top_category":top_category,"top_mode":top_mode,"top_penalty":top_penalty}

def get_bias_breakdown(user_id: int):
    import pandas as pd
    df = export_decisions_df(user_id)
    counters = {"Viés de confirmação":0,"Efeito manada":0,"Aversão à perda":0,"Ego/excesso de confiança":0,"Ancoragem":0,"Alerta de viés (rápido)":0}
    if df.empty or "inputs_json" not in df.columns:
        return pd.DataFrame(columns=["bias_name","total"])
    for raw in df["inputs_json"].dropna().tolist():
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if data.get("bias_confirmation"): counters["Viés de confirmação"] += 1
        if data.get("bias_herd"): counters["Efeito manada"] += 1
        if data.get("bias_loss"): counters["Aversão à perda"] += 1
        if data.get("bias_ego"): counters["Ego/excesso de confiança"] += 1
        if data.get("bias_anchor"): counters["Ancoragem"] += 1
        if data.get("bias_alert") == "Sim": counters["Alerta de viés (rápido)"] += 1
    rows = [{"bias_name":k,"total":v} for k,v in counters.items() if v > 0]
    return pd.DataFrame(rows).sort_values(["total","bias_name"], ascending=[False, True]) if rows else pd.DataFrame(columns=["bias_name","total"])
