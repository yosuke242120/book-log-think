"""
Book Log & Think — Streamlit メインアプリ (バグ修正版)
"""
import streamlit as st
import pandas as pd
from datetime import date, datetime
import gspread
from google.oauth2.service_account import Credentials
from logic import is_alert, validate_dates
import plotly.express as px

# ── Google Sheets 接続 ──────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "BookLogAndThink"
WORKSHEET  = "books"

@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    client = gspread.authorize(creds)
    sh = client.open(SHEET_NAME) 
    try:
        return sh.worksheet(WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET, rows=500, cols=10)
        ws.append_row(["id","title","author","category","status","start_date","end_date","note"])
        return ws

def load_books(ws) -> pd.DataFrame:
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame(columns=["id","title","author","category","status","start_date","end_date","note"])
    df = pd.DataFrame(data)
    # IDを確実に数値として扱う
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date
    df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce").dt.date
    return df

def save_all(ws, df: pd.DataFrame):
    ws.clear()
    # 数値を文字列に変換する前に、空データを徹底的に処理
    df2 = df.copy()
    df2["start_date"] = df2["start_date"].apply(lambda x: str(x) if pd.notnull(x) and x != "" else "")
    df2["end_date"]   = df2["end_date"].apply(lambda x: str(x) if pd.notnull(x) and x != "" else "")
    df2 = df2.fillna("")
    
    # スプレッドシートに書き込み
    ws.update([df2.columns.tolist()] + df2.values.tolist())

# ── ページ設定 ──
st.set_page_config(page_title="Book Log & Think", page_icon="📚", layout="wide")

# 🔐 簡易認証
if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔐 Login")
    pwd = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("😕 パスワードが違います")
    st.stop() 

# ── メイン画面 ──
st.title("📚 Book Log & Think")
st.caption("読書記録 & 振り返りログ")

CATEGORIES = ["小説", "自己啓発", "ビジネス", "投資関連"]
STATUSES   = ["未読", "読書中", "読了"]
STATUS_MAP = {"未読": "unread", "読書中": "reading", "読了": "done"}
STATUS_RMAP= {v: k for k, v in STATUS_MAP.items()}

ws = get_worksheet()
df = load_books(ws)

# ── サマリー & グラフ ──
col1, col2, col3, col4 = st.columns(4)
col1.metric("総登録数", len(df))
col2.metric("未読",     len(df[df.status == "unread"]))
col3.metric("読書中",   len(df[df.status == "reading"]))
col4.metric("読了",     len(df[df.status == "done"]))

if not df.empty:
    cat_counts = df["category"].value_counts().reset_index()
    cat_counts.columns = ["分類", "冊数"]
    fig = px.pie(cat_counts, values="冊数", names="分類", title="読書分類の割合", hole=0.4)
    fig.update_layout(height=350, margin=dict(t=50, b=0))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── フィルタ & 一覧表示 ──
fcol1, fcol2 = st.columns(2)
f_status = fcol1.selectbox("表示ステータスで絞り込み", ["すべて"] + STATUSES)
f_cat    = fcol2.selectbox("表示分類で絞り込み", ["すべて"] + CATEGORIES)

view = df.copy()
if f_status != "すべて": view = view[view.status == STATUS_MAP[f_status]]
if f_cat != "すべて":    view = view[view.category == f_cat]

today = date.today()
def make_display(row):
    alert = is_alert(row["status"], row["start_date"], today)
    days  = (today - row["start_date"]).days if pd.notnull(row["start_date"]) and row["status"] == "reading" else None
    return pd.Series({
        "ID": row["id"],
        "⚠️": "⚠️ 21日経過" if alert else "",
        "タイトル": row["title"],
        "著者": row["author"],
        "分類": row["category"],
        "ステータス": STATUS_RMAP.get(row["status"], row["status"]),
        "経過日数": f"{days}日" if days is not None else "",
        "読了日": str(row["end_date"]) if pd.notnull(row["end_date"]) else "",
        "感想": row["note"],
        "_alert": alert
    })

if not view.empty:
    disp = view.apply(make_display, axis=1)
    st.dataframe(disp.drop(columns=["_alert"]).style.apply(lambda r: ["background-color: #fff0f0"]*len(r) if r["⚠️"] else ["" Japanese]*len(r), axis=1), use_container_width=True, hide_index=True) # indexを隠す
else:
    st.info("該当する本がありません。")

st.divider()

# ── 登録・編集フォーム ──
with st.expander("➕ 本を追加 / 編集する"):
    # IDを明示的に表示して選択ミスを防ぐ
    options = ["新規追加"] + [f"ID:{row['id']} - {row['title']}" for _, row in df.iterrows()]
    edit_sel_label = st.selectbox("編集する本を選択（新規の場合は「新規追加」）", options)

    if edit_sel_label == "新規追加":
        init = {"id": None, "title":"","author":"","category":CATEGORIES[0],"status":"未読","start_date":None,"end_date":None,"note":""}
    else:
        target_id = int(edit_sel_label.split(" - ")[0].replace("ID:", ""))
        row = df[df["id"] == target_id].iloc[0]
        init = row.to_dict()
        init["status"] = STATUS_RMAP.get(init["status"], init["status"])

    with st.form("book_form"):
        title = st.text_input("タイトル *", value=init["title"])
        author = st.text_input("著者 *", value=init["author"])
        cat = st.selectbox("分類 *", CATEGORIES, index=CATEGORIES.index(init["category"]) if init["category"] in CATEGORIES else 0)
        status = st.selectbox("ステータス *", STATUSES, index=STATUSES.index(init["status"]) if init["status"] in STATUSES else 0)
        start_date = st.date_input("読書開始日", value=init["start_date"] or date.today()) if status in ["読書中","読了"] else None
        end_date = st.date_input("読了日", value=init["end_date"] or date.today()) if status == "読了" else None
        note = st.text_area("感想・言語化", value=init["note"])
        submitted = st.form_submit_button("保存する")

    if submitted:
        if not title or not author:
            st.error("タイトルと著者は必須です")
        else:
            status_en = STATUS_MAP[status]
            if edit_sel_label == "新規追加":
                new_id = int(df["id"].max()) + 1 if not df.empty else 1
                new_row = pd.DataFrame([{"id": new_id, "title": title, "author": author, "category": cat, "status": status_en, "start_date": start_date, "end_date": end_date, "note": note}])
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                idx = df[df["id"] == target_id].index[0]
                df.at[idx, "title"] = title
                df.at[idx, "author"] = author
                df.at[idx, "category"] = cat
                df.at[idx, "status"] = status_en
                df.at[idx, "start_date"] = start_date
                df.at[idx, "end_date"] = end_date
                df.at[idx, "note"] = note
            save_all(ws, df)
            st.success("保存完了！")
            st.rerun()

# ── 削除 ──
with st.expander("🗑 本を削除する"):
    del_options = ["選択してください"] + [f"ID:{row['id']} - {row['title']}" for _, row in df.iterrows()]
    del_sel = st.selectbox("削除する本を選択", del_options)
    if st.button("削除を実行") and del_sel != "選択してください":
        target_id = int(del_sel.split(" - ")[0].replace("ID:", ""))
        df = df[df["id"] != target_id]
        save_all(ws, df)
        st.success("削除完了")
        st.rerun()