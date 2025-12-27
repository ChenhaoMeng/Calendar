import streamlit as st
import json
import pandas as pd
from github import Github, Auth
from openai import OpenAI
from datetime import datetime
import plotly.express as px
import re
from streamlit_calendar import calendar

# ==========================================
# 1. 界面配置与深度 CSS 美化
# ==========================================
st.set_page_config(
    page_title="DeepSeek Life OS v2",
    page_icon="🌊",
    layout="wide"
)

st.markdown("""
<style>
    /* 1.1 全局背景与字体 */
    .stApp {
        background: linear-gradient(160deg, #f0faff 0%, #e0f2f1 50%, #e1f5fe 100%) !important;
    }
    
    * {
        font-family: 'Inter', 'Segoe UI', sans-serif !important;
        color: #1a5f7a !important;
    }

    /* 1.2 唤起式指令中心容器 */
    .magic-box {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(15px);
        border: 2px solid #b2ebf2;
        border-radius: 25px;
        padding: 20px;
        box-shadow: 0 10px 30px rgba(0, 188, 212, 0.1);
        margin-bottom: 30px;
    }

    /* 1.3 玻璃卡片样式 */
    .glass-card {
        background: rgba(255, 255, 255, 0.55);
        backdrop-filter: blur(12px);
        border-radius: 18px;
        border: 1px solid rgba(255, 255, 255, 0.8);
        padding: 20px;
        margin-bottom: 20px;
        transition: all 0.3s ease;
    }
    .glass-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.05);
    }

    /* 1.4 Tab 样式自定义 */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent !important;
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: rgba(255,255,255,0.4) !important;
        border-radius: 10px 10px 0 0 !important;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4dd0e1 !important;
        color: white !important;
    }

    /* 1.5 按钮与输入框 */
    div.stButton > button {
        background: linear-gradient(90deg, #4dd0e1, #26c6da) !important;
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        transition: 0.3s;
    }
    div.stButton > button:hover { opacity: 0.9; transform: scale(1.02); }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据与 AI 核心引擎
# ==========================================
try:
    G_TOKEN, G_REPO, DS_KEY = st.secrets["GITHUB_TOKEN"], st.secrets["REPO_NAME"], st.secrets["DEEPSEEK_API_KEY"]
except:
    st.error("🔑 请在 Secrets 中配置 GITHUB_TOKEN, REPO_NAME, DEEPSEEK_API_KEY"); st.stop()

@st.cache_resource
def init_clients():
    return OpenAI(api_key=DS_KEY, base_url="https://api.deepseek.com"), Github(auth=Auth.Token(G_TOKEN)).get_repo(G_REPO)

ai_client, repo = init_clients()

class DataStore:
    def __init__(self, path): self.path = path
    def load(self):
        try:
            c = repo.get_contents(self.path)
            return json.loads(c.decoded_content.decode()), c.sha
        except: return [], None
    def save(self, data, sha, msg="Update"):
        content = json.dumps(data, indent=4, ensure_ascii=False)
        if sha: repo.update_file(self.path, msg, content, sha)
        else: repo.create_file(self.path, "Init", content)

db_cal, db_fin, db_note = DataStore("events.json"), DataStore("finance.json"), DataStore("notes.json")

def universal_ai_parser(text):
    """万能解析器：判断意图并提取结构化数据"""
    now = datetime.now()
    prompt = f"""
    当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} (24小时制)。
    目标: 解析 "{text}" 归类到 calendar/finance/note 之一。
    
    返回 JSON 格式:
    1. 日程 (calendar): {{"type":"calendar", "data": [{{"title":"名称", "start":"YYYY-MM-DDTHH:MM:SS", "end":"YYYY-MM-DDTHH:MM:SS"}}]}}
       - 必须使用 24 小时制 ISO 格式。
       - 下午3点 -> 15:00:00。
    2. 财务 (finance): {{"type":"finance", "data": {{"item":"名称", "amount":数字, "category":"类别", "date":"YYYY-MM-DD"}}}}
       - 支出为负，收入为正。
    3. 笔记 (note): {{"type":"note", "data": {{"content":"内容", "date":"YYYY-MM-DD HH:MM"}}}}
    """
    try:
        resp = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={ 'type': 'json_object' }
        )
        return json.loads(resp.choices[0].message.content)
    except: return None

# ==========================================
# 3. 顶部唤起式指令中心
# ==========================================
st.markdown('<div class="magic-box">', unsafe_allow_html=True)
user_cmd = st.chat_input("✨ 唤起 AI 指令：'明早8点开会'、'晚饭打车32元'、'记个灵感：DeepSeek太强了'")
st.markdown('</div>', unsafe_allow_html=True)

if user_cmd:
    with st.spinner("🤖 AI 处理中..."):
        res = universal_ai_parser(user_cmd)
        if res:
            if res['type'] == 'calendar':
                data, sha = db_cal.load()
                data.extend(res['data'])
                db_cal.save(data, sha, "AI Calendar")
                st.toast("📅 已添加到日历 (24h制)", icon="✅")
            elif res['type'] == 'finance':
                data, sha = db_fin.load()
                data.append(res['data'])
                db_fin.save(data, sha, "AI Finance")
                st.toast(f"💰 已记账: {res['data']['amount']}", icon="💸")
            elif res['type'] == 'note':
                data, sha = db_note.load()
                data.insert(0, res['data'])
                db_note.save(data, sha, "AI Note")
                st.toast("📝 灵感已存入胶囊", icon="💡")
            # 延迟一下刷新，让用户看清 Toast
            st.rerun()

# ==========================================
# 4. 主内容区
# ==========================================
tabs = st.tabs(["📅 24H 智能日历", "💰 财务看板", "📝 灵感胶囊"])

# --- Tab 1: 日历 (强化 24h) ---
with tabs[0]:
    events, sha_cal = db_cal.load()
    c1, c2 = st.columns([8, 2])
    
    with c1:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        calendar_options = {
            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek,listWeek"},
            "initialView": "timeGridWeek", # 默认显示周视图更利于看时间线
            "slotMinTime": "00:00:00",
            "slotMaxTime": "24:00:00",
            "hour12": False, # 强制日历不使用 AM/PM
            "locale": "zh-cn",
            "slotLabelFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False}, # 侧边轴 24h
            "eventTimeFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False, "meridiem": False}, # 事件块 24h
            "allDaySlot": False,
            "height": 700
        }
        calendar(events=events, options=calendar_options, key="calendar_v2")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<p style="font-weight:bold; font-size:1.2em;">📋 近期安排</p>', unsafe_allow_html=True)
        if events:
            df_cal = pd.DataFrame(events).sort_values('start', ascending=False)
            # 格式化显示 24h 字符串
            df_cal['24H时间'] = df_cal['start'].str.replace('T', ' ').str[5:16]
            st.dataframe(df_cal[['24H时间', 'title']], hide_index=True, use_container_width=True)
            if st.button("清空所有日程", type="secondary"):
                db_cal.save([], sha_cal, "Clear All")
                st.rerun()

# --- Tab 2: 财务 (数据可视化) ---
with tabs[1]:
    f_data, sha_f = db_fin.load()
    if f_data:
        df_f = pd.DataFrame(f_data)
        df_f['amount'] = pd.to_numeric(df_f['amount'])
        
        # 指标卡
        m1, m2, m3 = st.columns(3)
        m1.metric("结余", f"¥{df_f['amount'].sum():,.2f}")
        m2.metric("本月支出", f"¥{abs(df_f[df_f['amount']<0]['amount'].sum()):,.2f}")
        m3.metric("本月收入", f"¥{df_f[df_f['amount']>0]['amount'].sum():,.2f}")
        
        col_f1, col_f2 = st.columns([6, 4])
        with col_f1:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            fig = px.line(df_f, x='date', y='amount', title="资金流水 (24H 记账体系)")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with col_f2:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.dataframe(df_f.sort_values('date', ascending=False), height=400, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

# --- Tab 3: 灵感 (瀑布流) ---
with tabs[2]:
    n_data, sha_n = db_note.load()
    st.markdown('<div style="column-count: 2; column-gap: 20px;">', unsafe_allow_html=True)
    for i, n in enumerate(n_data):
        st.markdown(f"""
        <div class="glass-card" style="display: inline-block; width: 100%;">
            <div style="color:#888; font-size:0.8em; margin-bottom:8px;">🕒 {n.get('date')} (24H)</div>
            <div style="font-size:1.1em; color:#00796b;">{n.get('content')}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    if n_data and st.button("清除所有笔记"):
        db_note.save([], sha_n, "Clear Notes")
        st.rerun()

# ==========================================
# 5. 交互后续
# ==========================================
st.sidebar.markdown(f"### 🌊 DeepSeek OS\n**状态**: 运行中\n**时间**: {datetime.now().strftime('%H:%M:%S')}")
