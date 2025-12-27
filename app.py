import streamlit as st
import json
import pandas as pd
from github import Github
from openai import OpenAI
from datetime import datetime, timedelta
import plotly.express as px
import re
from streamlit_calendar import calendar  # 引入日历组件

# --- 1. 配置与初始化 ---
st.set_page_config(page_title="DeepSeek AI 助理", page_icon="🦈", layout="wide")

# 简洁的 Secrets 获取逻辑 (不再打印调试信息)
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    st.error("❌ 配置丢失，请检查 Secrets")
    st.stop()

# 初始化 DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

# --- 工具函数 ---
def clean_json_string(s):
    if not s: return ""
    s = re.sub(r"```json\s*", "", s)
    s = re.sub(r"```", "", s)
    return s.strip()

# --- 2. GitHub 数据管理器 ---
class DataManager:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.g = Github(GITHUB_TOKEN)
            self.repo = self.g.get_repo(REPO_NAME)
        except Exception as e:
            st.error(f"GitHub 连接失败: {e}")

    def load(self):
        try:
            contents = self.repo.get_contents(self.filename)
            return json.loads(contents.decoded_content.decode()), contents.sha
        except:
            return [], None

    def save(self, new_data_list, sha, commit_msg="Update data"):
        try:
            content_str = json.dumps(new_data_list, indent=4, ensure_ascii=False)
            if sha:
                self.repo.update_file(path=self.filename, message=commit_msg, content=content_str, sha=sha)
            else:
                self.repo.create_file(path=self.filename, message="Init file", content=content_str)
            return True
        except Exception as e:
            st.error(f"保存失败: {e}")
            return False

# 初始化
calendar_db = DataManager("events.json")
notes_db = DataManager("notes.json")
finance_db = DataManager("finance.json")

# --- 3. AI 智能处理 ---
def ai_parse_finance(text):
    prompt = f"""
    分析: "{text}"。提取记账JSON(不要Markdown):
    - item: 内容
    - amount: 金额(数字,支出为负)
    - category: 类别
    - date: YYYY-MM-DD (默认{datetime.now().strftime('%Y-%m-%d')})
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "只输出JSON"}, {"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(clean_json_string(response.choices[0].message.content))
    except: return None

def ai_parse_calendar(text):
    current = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    prompt = f"""
    当前: {current}。分析: "{text}"。提取日程JSON(不要Markdown):
    - title: 标题
    - date: YYYY-MM-DD
    - time: HH:MM (若未提及则为空字符串)
    - location: 地点
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "只输出JSON"}, {"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(clean_json_string(response.choices[0].message.content))
    except: return None

# --- 4. 界面构建 ---
st.title("🦈 DeepSeek 智能助理")

tab1, tab2, tab3 = st.tabs(["📅 日程日历", "💰 极速记账", "📝 灵感备忘"])

# ================= Tab 1: 可视化日历 (大幅升级) =================
with tab1:
    col1, col2 = st.columns([1, 3]) # 左侧输入，右侧大日历
    
    with col1:
        st.subheader("➕ 添加")
        cal_input = st.text_area("输入计划 (如: 周五晚8点去看电影)", height=150)
        if st.button("智能添加", use_container_width=True, type="primary"):
            if cal_input:
                with st.spinner("AI 正在安排..."):
                    event = ai_parse_calendar(cal_input)
                    if event:
                        data, sha = calendar_db.load()
                        data.insert(0, event)
                        if calendar_db.save(data, sha, "Add event"):
                            st.success("✅ 添加成功")
                            st.rerun()
                    else:
                        st.error("AI 解析失败，请重试")

    with col2:
        # --- 核心：渲染日历组件 ---
        events_data, _ = calendar_db.load()
        
        # 1. 数据转换：把 GitHub 的数据格式转为 Calendar 组件需要的格式
        calendar_events = []
        for e in events_data:
            # 构造 ISO 格式的时间字符串
            start_str = e.get('date')
            if e.get('time'):
                start_str += f"T{e.get('time')}"
            
            # 定义事件颜色 (随机或固定)
            calendar_events.append({
                "title": f"{e.get('time', '')} {e.get('title')}",
                "start": start_str,
                "backgroundColor": "#3788d8", # 蓝色背景
                "borderColor": "#3788d8",
                "extendedProps": {"location": e.get('location')} # 额外信息
            })

        # 2. 配置日历外观
        calendar_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,timeGridDay"
            },
            "initialView": "dayGridMonth",
            "navLinks": True,
            "selectable": True,
            "nowIndicator": True,
        }

        # 3. 显示日历
        if calendar_events:
            st.markdown("### 🗓️ 我的日程表")
            calendar(events=calendar_events, options=calendar_options, key="my_calendar")
        else:
            st.info("👋 日历是空的，快在左边添加第一条日程吧！")

# ================= Tab 2: 记账 (保持原有逻辑) =================
with tab2:
    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        fin_input = st.text_input("输入消费:", placeholder="例如: 超市买菜60元")
    with f_col2:
        if st.button("记账", type="primary"):
            if fin_input:
                record = ai_parse_finance(fin_input)
                if record:
                    data, sha = finance_db.load()
                    data.append(record)
                    finance_db.save(data, sha)
                    st.rerun()

    fin_data, _ = finance_db.load()
    if fin_data:
        df_fin = pd.DataFrame(fin_data)
        st.metric("本月结余", f"¥{df_fin['amount'].sum():.2f}")
        
        c1, c2 = st.columns(2)
        with c1:
            df_exp = df_fin[df_fin['amount'] < 0].copy()
            if not df_exp.empty:
                df_exp['abs'] = df_exp['amount'].abs()
                st.plotly_chart(px.pie(df_exp, values='abs', names='category', hole=0.4), use_container_width=True)
        with c2:
            st.dataframe(df_fin[['date', 'item', 'amount', 'category']].sort_values('date', ascending=False), hide_index=True, use_container_width=True)

# ================= Tab 3: 备忘 (保持原有逻辑) =================
with tab3:
    with st.form("note"):
        c1, c2 = st.columns([3, 1])
        content = c1.text_input("内容")
        tags = c2.text_input("标签")
        if st.form_submit_button("保存"):
            if content:
                new_note = {"content": content, "tags": tags.split(), "created_at": datetime.now().strftime("%Y-%m-%d")}
                data, sha = notes_db.load()
                data.insert(0, new_note)
                notes_db.save(data, sha)
                st.rerun()
    
    notes, _ = notes_db.load()
    for n in notes:
        st.markdown(f"**{n['created_at']}**: {n['content']} `{' '.join(n.get('tags',[]))}`")
        st.divider()
