"""
Book Log & Think — Streamlit メインアプリ (グラフ表示版)
"""
import streamlit as st
import pandas as pd
from datetime import date, datetime
import gspread
from google.oauth2.service_account import Credentials
from logic import is_alert, validate_dates
import plotly.express as px  # グラフ用に追加

# ── Google Sheets 接続 ──────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHEET_NAME = "BookLogAndThink"   # スプレッドシート名
WORKSHEET  = "books"             # シート名

@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
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
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date
    df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce").dt.date
    return df

def save_all(ws, df: pd.DataFrame):
    ws.clear()
    df2 = df.fillna("").copy()
    df2["start_date"] = df2["start_date"].astype(str).replace("NaT", "")
    df2["end_date"]   = df2["end_date"].astype(str).replace("NaT", "")
    ws.update([df2.columns.tolist()] + df2.values.tolist())

# ── ページ設定 ──
st.set_page_config(page_title="Book Log & Think", page_icon="📚", layout="wide")

# 🔐 簡易認証機能
if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔐 Login")
    pwd = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("😕 パスワードが違います")
    st.stop() 

# ── ここからメイン画面 ──────────────────────────────────────────────────
st.title("📚 Book Log & Think")
st.caption("読書記録 & 振り返りログ")

CATEGORIES = ["小説", "自己啓発", "ビジネス", "投資関連"]
STATUSES   = ["未読", "読書中", "読了"]
STATUS_MAP = {"未読": "unread", "読書中": "reading", "読了": "done"}
STATUS_RMAP= {v: k for k, v in STATUS_MAP.items()}

# データ読み込み
ws = get_worksheet()
df = load_books(ws)

# ── サマリー ───────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("総登録数", len(df))
col2.metric("未読",     len(df[df.status == "unread"]))
col3.metric("読書中",   len(df[df.status == "reading"]))
col4.metric("読了",     len(df[df.status == "done"]))

# 📊 追加機能：分類の割合グラフ
if not df.empty:
    cat_counts = df["category"].value_counts().reset_index()
    cat_counts.columns = ["分類", "冊数"]
    
    fig = px.pie(cat_counts, values="冊数", names="分類", 
                 title="読書分類の割合",
                 hole=0.4,
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    
    fig.update_layout(margin=dict(t=50, b=0, l=0, r=0), height=350)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── フィルタ ───────────────────────────────────────────────────────
fcol1, fcol2 = st.columns(2)
f_status = fcol1.selectbox("ステータス", ["すべて"] + STATUSES)
f_cat    = fcol2.selectbox("分類",       ["すべて"] + CATEGORIES)

view = df.copy()
if f_status != "すべて":
    view = view[view.status == STATUS_MAP[f_status]]
if f_cat != "すべて":
    view = view[view.category == f_cat]

# ── アラート判定 & 表示 ────────────────────────────────────────────
today = date.today()

def make_display(row):
    alert = is_alert(row["status"], row["start_date"], today)
    days  = (today - row["start_date"]).days if pd.notnull(row["start_date"]) and row["status"] == "reading" else None
    return pd.Series({
        "⚠️": "⚠️ 21日超過" if alert else "",
        "タイトル":   row["title"],
        "著者":       row["author"],
        "分類":       row["category"],
        "ステータス": STATUS_RMAP.get(row["status"], row["status"]),
        "経過日数":   f"{days}日" if days is not None else "",
        "読書開始日": str(row["start_date"]) if pd.notnull(row["start_date"]) else "",
        "読了日":      str(row["end_date"])   if pd.notnull(row["end_date"])   else "",
        "感想":       row["note"] if row["note"] else "",
        "_id":         row["id"],
        "_alert":      alert,
    })

if not view.empty:
    disp = view.apply(make_display, axis=1)
    alert_ids = disp[disp["_alert"]]["_id"].tolist()
    show_cols = ["⚠️","タイトル","著者","分類","ステータス","経過日数","読書開始日","読了日","感想"]

    def highlight(row):
        color = "background-color: #fff0f0" if row["⚠️"] else ""
        return [color] * len(row)

    st.dataframe(
        disp[show_cols].style.apply(highlight, axis=1),
        use_container_width=True,
        height=400,
    )
    if alert_ids:
        st.warning(f"⚠️ {len(alert_ids)}冊の本が21日を超えて読書中です。継続を確認してください。")
else:
    st.info("該当する本がありません。")

st.divider()

# ── 登録フォーム ───────────────────────────────────────────────────
with st.expander("➕ 本を追加 / 編集する"):
    edit_ids = ["新規追加"] + df["id"].astype(str).tolist()
    edit_sel = st.selectbox("編集する本のID（新規の場合は「新規追加」）", edit_ids)

    if edit_sel == "新規追加":
        init = {"title":"","author":"","category":CATEGORIES[0],"status":"unread","start_date":None,"end_date":None,"note":""}
    else:
        row = df[df["id"] == int(edit_sel)].iloc[0]
        init = row.to_dict()

    with st.form("book_form"):
        title  = st.text_input("タイトル *", value=init["title"])
        author = st.text_input("著者 *",     value=init["author"])
        cat    = st.selectbox("分類 *", CATEGORIES, index=CATEGORIES.index(init["category"]) if init["category"] in CATEGORIES else 0)
        status = st.selectbox("ステータス *", STATUSES, index=["unread","reading","done"].index(init["status"]) if init["status"] in ["unread","reading","done"] else 0)
        start_date = st.date_input("読書開始日", value=init["start_date"] or date.today()) if status in ["読書中","読了"] else None
        end_date   = st.date_input("読了日 *",  value=init["end_date"]   or date.today()) if status == "読了"  else None
        note       = st.text_area("感想・言語化", value=init["note"] or "")
        submitted  = st.form_submit_button("保存する")

    if submitted:
        errors = []
        if not title:  errors.append("タイトルを入力してください")
        if not author: errors.append("著者を入力してください")
        if status == "読了" and not end_date: errors.append("読了日は必須です")
        date_err = validate_dates(start_date, end_date)
        if date_err: errors.append(date_err)

        if errors:
            for e in errors: st.error(e)
        else:
            status_en = STATUS_MAP[status]
            if edit_sel == "新規追加":
                new_id = int(df["id"].max()) + 1 if not df.empty else 1
                new_row = pd.DataFrame([{
                    "id": new_id, "title": title, "author": author,
                    "category": cat, "status": status_en,
                    "start_date": start_date, "end_date": end_date, "note": note
                }])
                df = pd.concat([df, new_row], ignore_index=True)
            else:
                idx = df[df["id"] == int(edit_sel)].index[0]
                df.at[idx, "title"]      = title
                df.at[idx, "author"]     = author
                df.at[idx, "category"]   = cat
                df.at[idx, "status"]     = status_en
                df.at[idx, "start_date"] = start_date
                df.at[idx, "end_date"]   = end_date
                df.at[idx, "note"]       = note

            save_all(ws, df)
            st.success("保存しました！")
            st.rerun()

# ── 削除 ───────────────────────────────────────────────────────────
with st.expander("🗑 本を削除する"):
    del_id = st.selectbox("削除するIDを選択", ["選択してください"] + df["id"].astype(str).tolist())
    if st.button("削除する") and del_id != "選択してください":
        df = df[df["id"] != int(del_id)]
        save_all(ws, df)
        st.success("削除しました")
        st.rerun()