import streamlit as st
import json
import pandas as pd
from github import Github, Auth
from openai import OpenAI
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import re
from streamlit_calendar import calendar

# --- 1. 配置与页面初始化 ---
st.set_page_config(
    page_title="DeepSeek 智能助理 Pro",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 自定义 CSS 美化 ---
st.markdown("""
<style>
    /* 全局字体与背景优化 */
    .stApp {
        background-color: #f8f9fa;
    }
    
    /* 卡片式容器样式 */
    .css-card {
        border-radius: 15px;
        padding: 20px;
        background-color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    
    /* 统计指标样式 */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* 备忘录卡片样式 */
    .note-card {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 15px;
        margin-bottom: 10px;
        border-radius: 5px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    
    /* 按钮优化 */
    .stButton>button {
        border-radius: 20px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- Secrets 检查 ---
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except KeyError as e:
    st.error(f"❌ 配置丢失，请检查 Streamlit Secrets: {e}")
    st.stop()

# --- 缓存 OpenAI 客户端与 GitHub 连接 ---
@st.cache_resource
def get_openai_client():
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

@st.cache_resource
def get_github_repo():
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    return g.get_repo(REPO_NAME)

client = get_openai_client()

# --- 2. 数据管理类 (优化版) ---
class DataManager:
    def __init__(self, filename):
        self.filename = filename
        self.repo = get_github_repo()

    def load(self):
        try:
            contents = self.repo.get_contents(self.filename)
            sha = contents.sha
            try:
                data = json.loads(contents.decoded_content.decode())
                # 数据清洗：确保是最外层是列表
                if isinstance(data, dict): data = [data]
                if not isinstance(data, list): data = []
                return data, sha
            except json.JSONDecodeError:
                return [], sha
        except:
            return [], None

    def save(self, new_data_list, sha, commit_msg="Update data"):
        try:
            # 确保保存的是标准 JSON 格式
            content_str = json.dumps(new_data_list, indent=4, ensure_ascii=False)
            if sha:
                self.repo.update_file(path=self.filename, message=commit_msg, content=content_str, sha=sha)
            else:
                self.repo.create_file(path=self.filename, message="Init file", content=content_str)
            return True
        except Exception as e:
            st.toast(f"❌ 保存失败: {e}", icon="🚫")
            return False

# 初始化数据库
calendar_db = DataManager("events.json")
notes_db = DataManager("notes.json")
finance_db = DataManager("finance.json")

# --- 3. AI 智能处理核心 ---
def clean_json_string(s):
    """清洗 AI 返回的 JSON 字符串"""
    if not s: return ""
    s = re.sub(r"```json\s*", "", s)
    s = re.sub(r"```", "", s)
    return s.strip()

def ai_parse_finance(text):
    prompt = f"""
    当前年份: 2025。分析: "{text}"。
    请提取记账JSON (不要Markdown, 直接返回JSON):
    - item: 消费/收入内容
    - amount: 金额(数字类型。支出为负数，收入为正数)
    - category: 类别 (如: 餐饮, 交通, 工资, 购物)
    - date: YYYY-MM-DD (默认当天)
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(clean_json_string(response.choices[0].message.content))
    except: return None

def ai_parse_calendar(text):
    current_year = datetime.now().year
    prompt = f"""
    当前系统年份: {current_year}。
    请分析输入文本，它可能包含**多条**日程或考试安排。
    
    输入文本: "{text}"
    
    请提取所有事件并返回一个 JSON 列表 (Array)。即使只有一条，也必须包在列表里。
    每个事件包含:
    - title: 标题 (通常是课程名或事项名)
    - start: 格式必须为 "YYYY-MM-DDTHH:MM:SS" (24小时制)。
      例如输入 "2026-01-16(13:10-15:10)" 应解析为 "2026-01-16T13:10:00"。
    - end: 结束时间 (根据时间段推算)，格式同上。
    - location: 地点 (如 "东下院102")
    - allDay: false (如果有具体时间点)
    
    注意：优先使用文本中明确提到的年份(如2026)，不要强行改为当前年份。
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        # 解析返回的 JSON
        result = json.loads(clean_json_string(response.choices[0].message.content))
        
        # 容错处理：确保返回的一定是列表
        if isinstance(result, dict):
            return [result]
        return result
    except Exception as e:
        print(f"解析错误: {e}") 
        return []
# --- 4. 侧边栏 ---
with st.sidebar:
    st.title("🤖 助手控制台")
    st.info(f"📅 今天是: {datetime.now().strftime('%Y-%m-%d %A')}")
    st.markdown("---")
    st.markdown("### 💡 使用技巧")
    st.caption("1. 记账支持自然语言：'昨天发工资20000' 或 '打车花了50'")
    st.caption("2. 日历智能安排：'下周五下午3点开会'")
    st.markdown("---")
    if st.button("🔄 强制刷新数据"):
        st.cache_data.clear()
        st.rerun()

# --- 5. 主界面 ---
st.title("DeepSeek Personal Assistant")
st.markdown("##### 您的 2025 全能生活管家")

tab1, tab2, tab3 = st.tabs(["📅 智能日历", "💰 资产管家", "📝 灵感胶囊"])

# ================= Tab 1: 智能日历 =================
with tab1:
    col_input, col_cal = st.columns([1, 3])
    
    with col_input:
        st.markdown("### ⚡ 快速安排")
        with st.form("cal_form"):
            cal_txt = st.text_area("输入计划...", height=100, placeholder="例如：明天上午10点在公司开会")
            submitted = st.form_submit_button("添加日程", use_container_width=True, type="primary")
            
        if submitted and cal_txt:
            with st.spinner("🤖 AI 正在批量解析日程..."):
                new_events = ai_parse_calendar(cal_txt)
                
                if new_events and isinstance(new_events, list) and len(new_events) > 0:
                    data, sha = calendar_db.load()
                    
                    # 使用 extend 批量添加
                    data.extend(new_events)
                    
                    if calendar_db.save(data, sha):
                        st.toast(f"✅ 成功导入 {len(new_events)} 条日程！", icon="📅")
                        st.rerun()
                else:
                    st.error("无法识别日程，请检查输入格式")

        # 待办列表视图
        st.markdown("---")
        st.markdown("#### 📋 近期列表")
        events_data, _ = calendar_db.load()
        if events_data:
            # 简单的列表展示
            df_cal = pd.DataFrame(events_data)
            if 'start' in df_cal.columns:
                df_cal['start'] = pd.to_datetime(df_cal['start']).dt.strftime('%m-%d %H:%M')
                st.dataframe(
                    df_cal[['start', 'title', 'location']], 
                    hide_index=True, 
                    use_container_width=True,
                    column_config={"start": "时间", "title": "事项", "location": "地点"}
                )

    with col_cal:
        # 数据清洗与适配
        cal_events = []
        for e in events_data:
            if isinstance(e, dict) and e.get('start'):
                cal_events.append({
                    "title": e.get('title', '未命名'),
                    "start": e.get('start'),
                    "allDay": e.get('allDay', True),
                    "backgroundColor": "#4F46E5",
                    "borderColor": "#4F46E5",
                    "extendedProps": {"location": e.get('location', '')}
                })
        
        calendar_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,listWeek"
            },
            "initialView": "dayGridMonth",
            "navLinks": True,
            "selectable": True,
            "nowIndicator": True,
            "height": 650
        }
        calendar(events=cal_events, options=calendar_options, key="main_calendar")

# ================= Tab 2: 资产管家 =================
with tab2:
    # 顶部输入栏
    with st.container():
        c1, c2 = st.columns([3, 1])
        with c1:
            fin_input = st.chat_input("💬 告诉我要记什么? (例如: 超市购物128元 / 收到奖金5000)")
        if fin_input:
            with st.spinner("💰 正在入账..."):
                record = ai_parse_finance(fin_input)
                if record:
                    data, sha = finance_db.load()
                    data.append(record)
                    finance_db.save(data, sha)
                    st.toast(f"已记录: {record['item']} {record['amount']}", icon="✅")
                    st.rerun()

    fin_data, _ = finance_db.load()
    
    if fin_data:
        df_fin = pd.DataFrame(fin_data)
        df_fin['amount'] = pd.to_numeric(df_fin['amount'])
        df_fin['date'] = pd.to_datetime(df_fin['date'])
        
        # 顶部指标卡
        total_balance = df_fin['amount'].sum()
        total_income = df_fin[df_fin['amount'] > 0]['amount'].sum()
        total_expense = df_fin[df_fin['amount'] < 0]['amount'].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("总结余", f"¥{total_balance:,.2f}", delta_color="normal")
        m2.metric("本月收入", f"¥{total_income:,.2f}", delta=f"+{total_income}", delta_color="normal")
        m3.metric("本月支出", f"¥{abs(total_expense):,.2f}", delta=f"{total_expense}", delta_color="inverse")

        st.markdown("---")

        # 图表区域
        chart_col1, chart_col2 = st.columns([1, 1])
        
        with chart_col1:
            st.subheader("📊 支出构成")
            df_exp = df_fin[df_fin['amount'] < 0].copy()
            if not df_exp.empty:
                df_exp['abs_amount'] = df_exp['amount'].abs()
                fig_pie = px.pie(df_exp, values='abs_amount', names='category', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("暂无支出数据")

        with chart_col2:
            st.subheader("📈 资金流向")
            # 按日期聚合
            daily_stats = df_fin.groupby('date')['amount'].sum().reset_index().sort_values('date')
            fig_line = px.bar(daily_stats, x='date', y='amount', color='amount', 
                              color_continuous_scale=['#ff4b4b', '#1f77b4', '#28a745'])
            fig_line.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_line, use_container_width=True)

        # 详细表格 (带格式化)
        st.subheader("📜 账单明细")
        st.dataframe(
            df_fin[['date', 'category', 'item', 'amount']].sort_values('date', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": "日期",
                "category": "分类",
                "item": "明细",
                "amount": st.column_config.NumberColumn(
                    "金额",
                    format="¥%.2f",
                )
            }
        )
    else:
        st.info("👋 还没有账单，试着输入 '午餐吃了30元' 开始记账吧！")

# ================= Tab 3: 灵感胶囊 (卡片墙) =================
with tab3:
    c1, c2 = st.columns([3, 1])
    with c1:
        with st.form("note_form", clear_on_submit=True):
            col_txt, col_tag = st.columns([4, 1])
            new_content = col_txt.text_input("记录灵感...", placeholder="想到了什么好点子？")
            new_tags = col_tag.text_input("标签", placeholder="Work/Life")
            if st.form_submit_button("保存灵感", type="primary"):
                if new_content:
                    note = {
                        "content": new_content,
                        "tags": new_tags.split() if new_tags else ["未分类"],
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    data, sha = notes_db.load()
                    data.insert(0, note)
                    notes_db.save(data, sha)
                    st.rerun()

    # 删除功能的逻辑处理
    if "delete_note_idx" not in st.session_state:
        st.session_state.delete_note_idx = -1

    notes_data, sha = notes_db.load()

    # 瀑布流展示 (模拟)
    if notes_data:
        st.markdown("### 📌 笔记墙")
        
        # 将笔记分为两列展示
        cols = st.columns(2)
        
        for idx, note in enumerate(notes_data):
            with cols[idx % 2]:
                # 渲染卡片
                with st.container():
                    st.markdown(f"""
                    <div class="note-card">
                        <small style="color:gray">{note.get('created_at', '')}</small><br>
                        <strong style="font-size:1.1em">{note.get('content')}</strong><br>
                        <div style="margin-top:5px">
                            {' '.join([f'<span style="background:#fff;padding:2px 6px;border-radius:4px;font-size:0.8em">#{t}</span>' for t in note.get('tags', [])])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 删除按钮
                    if st.button("🗑️ 删除", key=f"del_{idx}"):
                        notes_data.pop(idx)
                        notes_db.save(notes_data, sha)
                        st.rerun()
    else:
        st.info("空空如也~ 随时记录你的想法。")
