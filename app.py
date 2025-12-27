import streamlit as st
import json
import pandas as pd
from github import Github, Auth  # 引入 Auth 用于修复警告
from openai import OpenAI
from datetime import datetime
import plotly.express as px
import re
from streamlit_calendar import calendar

# --- 1. 配置与初始化 ---
st.set_page_config(page_title="DeepSeek AI 助理", page_icon="🦈", layout="wide")

try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    st.error("❌ 配置丢失，请检查 Streamlit Secrets")
    st.stop()

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

# --- 2. GitHub 数据管理器 (已修复警告) ---
class DataManager:
    def __init__(self, filename):
        self.filename = filename
        try:
            # 【修复】使用 Auth.Token 消除 DeprecationWarning
            auth = Auth.Token(GITHUB_TOKEN)
            self.g = Github(auth=auth)
            self.repo = self.g.get_repo(REPO_NAME)
        except Exception as e:
            st.error(f"GitHub 连接失败: {e}")

    def load(self):
        try:
            contents = self.repo.get_contents(self.filename)
            data = json.loads(contents.decoded_content.decode())
            # 确保返回的是列表
            if not isinstance(data, list):
                return [], contents.sha
            return data, contents.sha
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
        # 这里的 return 必须确保是单个字典，而不是列表
        res = json.loads(clean_json_string(response.choices[0].message.content))
        if isinstance(res, list): # 如果 AI 返回了列表，取第一个
            return res[0] if res else None
        return res
    except: return None

# --- 4. 界面构建 ---
st.title("🦈 DeepSeek 智能助理")

tab1, tab2, tab3 = st.tabs(["📅 日程日历", "💰 极速记账", "📝 灵感备忘"])

# ================= Tab 1: 日历 (强力修复版) =================
with tab1:
    col1, col2 = st.columns([1, 3]) 
    
    with col1:
        st.subheader("➕ 添加")
        cal_input = st.text_area("输入计划...", height=150)
        if st.button("智能添加", use_container_width=True, type="primary"):
            if cal_input:
                with st.spinner("AI 正在安排..."):
                    event = ai_parse_calendar(cal_input)
                    if event and isinstance(event, dict): # 确保是字典
                        data, sha = calendar_db.load()
                        data.insert(0, event)
                        if calendar_db.save(data, sha, "Add event"):
                            st.success("✅ 添加成功")
                            st.rerun()
                    else:
                        st.error("AI 解析结果异常，请重试")

    with col2:
        events_data, _ = calendar_db.load()
        
        calendar_events = []
        
        # --- 【核心修复】数据清洗循环 ---
        # 无论 events_data 里混入了什么奇怪的东西，这个循环都能处理
        clean_events = []
        
        # 1. 先把数据拍平 (Handle nested lists)
        for item in events_data:
            if isinstance(item, dict):
                clean_events.append(item)
            elif isinstance(item, list):
                # 如果是列表套列表，把里面的东西拿出来
                for sub_item in item:
                    if isinstance(sub_item, dict):
                        clean_events.append(sub_item)
        
        # 2. 再生成日历数据
        for e in clean_events:
            start_str = e.get('date')
            if not start_str: continue # 没有日期就跳过
            
            if e.get('time'):
                start_str += f"T{e.get('time')}"
            
            calendar_events.append({
                "title": f"{e.get('time', '')} {e.get('title', '无标题')}",
                "start": start_str,
                "backgroundColor": "#3788d8",
                "borderColor": "#3788d8",
                "extendedProps": {"location": e.get('location', '')}
            })

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

        if calendar_events:
            st.markdown("### 🗓️ 我的日程表")
            calendar(events=calendar_events, options=calendar_options, key="my_calendar")
        else:
            st.info("👋 日历是空的，或数据格式正在自动修复中...")

# ================= Tab 2: 记账 (保持不变) =================
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

# ================= Tab 3: 备忘 (保持不变) =================
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
