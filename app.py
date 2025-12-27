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
# 1. 系统配置与 CSS 深度美化 (强制覆盖)
# ==========================================
st.set_page_config(
    page_title="DeepSeek Life OS",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 注入 CSS：强制水蓝风格，覆盖 Streamlit 默认暗黑/浅色模式，并修复日历组件样式
st.markdown("""
<style>
    /* --- 全局背景 (强制水蓝渐变) --- */
    .stApp {
        background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 50%, #80deea 100%) !important;
        background-attachment: fixed !important;
    }
    
    /* --- 字体颜色 (深青色，保证对比度) --- */
    h1, h2, h3, h4, h5, h6, p, div, span, label, li {
        color: #006064 !important;
        font-family: 'Helvetica Neue', sans-serif;
    }

    /* --- 毛玻璃容器 (核心卡片样式) --- */
    .glass-card {
        background: rgba(255, 255, 255, 0.65);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.8);
        box-shadow: 0 8px 32px 0 rgba(0, 150, 136, 0.1);
        padding: 24px;
        margin-bottom: 24px;
    }

    /* --- 输入框与表格美化 --- */
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: rgba(255, 255, 255, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 1) !important;
        border-radius: 12px !important;
        color: #004d40 !important;
    }
    div[data-testid="stDataEditor"] {
        background-color: rgba(255, 255, 255, 0.5);
        border-radius: 12px;
        overflow: hidden;
    }

    /* --- 按钮美化 (水蓝渐变) --- */
    div.stButton > button {
        background: linear-gradient(45deg, #26c6da, #00acc1) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.5rem 1rem !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 10px rgba(0, 172, 193, 0.3) !important;
        transition: transform 0.2s;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
    }

    /* --- FullCalendar 日历组件深度覆盖 --- */
    /* 标题栏 */
    .fc .fc-toolbar-title { color: #006064 !important; font-size: 1.5rem !important; }
    /* 按钮 */
    .fc .fc-button-primary {
        background-color: rgba(255,255,255,0.6) !important;
        color: #006064 !important;
        border: none !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .fc .fc-button-active { background-color: #00bcd4 !important; color: white !important; }
    /* 表头 */
    .fc-col-header-cell-cushion { color: #00838f !important; }
    .fc-daygrid-day-number { color: #006064 !important; }
    /* 事件块 */
    .fc-event {
        border-radius: 6px !important;
        border: none !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 数据库与连接管理
# ==========================================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    st.error("❌ 配置丢失，请检查 Streamlit Secrets")
    st.stop()

@st.cache_resource
def get_client():
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

@st.cache_resource
def get_repo():
    auth = Auth.Token(GITHUB_TOKEN)
    g = Github(auth=auth)
    return g.get_repo(REPO_NAME)

client = get_client()

class DataManager:
    """处理 GitHub JSON 文件读写"""
    def __init__(self, filename):
        self.filename = filename
        self.repo = get_repo()

    def load(self):
        """读取数据，返回 (data_list, sha)"""
        try:
            contents = self.repo.get_contents(self.filename)
            sha = contents.sha
            try:
                data = json.loads(contents.decoded_content.decode())
                if not isinstance(data, list): data = []
                return data, sha
            except:
                return [], sha
        except:
            return [], None

    def save(self, data, sha, msg="Update"):
        """保存数据"""
        try:
            content = json.dumps(data, indent=4, ensure_ascii=False)
            if sha:
                self.repo.update_file(self.filename, msg, content, sha)
            else:
                self.repo.create_file(self.filename, "Init", content)
            return True
        except Exception as e:
            st.toast(f"保存失败: {e}", icon="🚫")
            return False

# 初始化实例
calendar_db = DataManager("events.json")
finance_db = DataManager("finance.json")
notes_db = DataManager("notes.json")

# ==========================================
# 3. AI 智能解析逻辑
# ==========================================
def clean_json_str(s):
    s = re.sub(r"```json\s*", "", s)
    s = re.sub(r"```", "", s)
    return s.strip()

def ai_parse_calendar(text):
    """解析日程，支持多条，强制24小时ISO格式"""
    prompt = f"""
    当前年份: {datetime.now().year} (如果文本提及明年则用明年)。
    任务: 分析文本 "{text}"，提取日程并返回 JSON 数组 (Array)。
    
    字段要求:
    1. start: 必须是 "YYYY-MM-DDTHH:MM:SS" (ISO 8601, 24小时制)。
       - 例如 "下午1点10分" -> "13:10:00"。
    2. end: 结束时间 (同上)。如果文本包含时间段 (如 13:00-15:00)，请计算出 end。
       - 如果未提及结束时间，默认持续 1 小时。
    3. title: 事件名称。
    4. location: 地点 (可选)。
    5. allDay: false (除非是全天节日)。
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        res = json.loads(clean_json_str(response.choices[0].message.content))
        return res if isinstance(res, list) else [res]
    except:
        return []

def ai_parse_finance(text):
    """解析记账，支持正负金额"""
    prompt = f"""
    当前时间: {datetime.now().strftime('%Y-%m-%d')}。
    任务: 分析 "{text}"，提取单条记账 JSON。
    
    字段要求:
    - item: 摘要
    - amount: 数字 (支出为负数，收入为正数)
    - category: 类别 (自动归类，如 餐饮/交通/工资)
    - date: YYYY-MM-DD
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(clean_json_str(response.choices[0].message.content))
    except:
        return None

# ==========================================
# 4. 主界面布局
# ==========================================
st.title("🌊 DeepSeek Life OS")

# 标签页导航
tab_cal, tab_fin, tab_note = st.tabs(["📅 智能日历", "💰 极速记账", "📝 灵感胶囊"])

# ------------------------------------------
# Tab 1: 日历系统 (View + Control)
# ------------------------------------------
with tab_cal:
    events_data, sha_cal = calendar_db.load()
    
    col_view, col_ctrl = st.columns([7, 3])
    
    # --- 左侧：日历视图 ---
    with col_view:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        # 格式转换
        fc_events = []
        for e in events_data:
            fc_events.append({
                "title": e.get('title', '无标题'),
                "start": e.get('start'),
                "end": e.get('end'),
                "backgroundColor": "#00bcd4", # 水蓝色
                "borderColor": "#00acc1",
                "extendedProps": {"location": e.get('location', '')}
            })
            
        calendar_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,listWeek"
            },
            "initialView": "dayGridMonth",
            "height": 650,
            "slotMinTime": "06:00:00", 
            "slotMaxTime": "24:00:00",
            "allDaySlot": False
        }
        calendar(events=fc_events, options=calendar_options, key="main_calendar")
        st.markdown('</div>', unsafe_allow_html=True)

    # --- 右侧：操作面板 ---
    with col_ctrl:
        # 1. 智能添加
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("⚡ 快速添加")
        with st.form("cal_add"):
            raw_text = st.text_area("输入...", height=100, 
                                  placeholder="支持粘贴多行课表\n或者：下周五下午3点开组会")
            if st.form_submit_button("解析并去重导入", use_container_width=True):
                if raw_text:
                    with st.spinner("🤖 AI 正在分析时间..."):
                        new_items = ai_parse_calendar(raw_text)
                        if new_items:
                            # 去重算法：生成唯一指纹 (开始时间+标题)
                            existing_fingerprints = {f"{e['start']}_{e['title']}" for e in events_data}
                            added_count = 0
                            
                            for item in new_items:
                                fp = f"{item.get('start')}_{item.get('title')}"
                                if fp not in existing_fingerprints:
                                    events_data.append(item)
                                    existing_fingerprints.add(fp) # 防止单次批量中自我重复
                                    added_count += 1
                            
                            if added_count > 0:
                                calendar_db.save(events_data, sha_cal, "Batch Add")
                                st.toast(f"已导入 {added_count} 条新日程！", icon="🎉")
                                st.rerun()
                            else:
                                st.warning("未发现新日程，均为重复项。")
                        else:
                            st.error("无法识别内容，请重试")
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. 批量管理 (删除)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("📋 批量管理")
        if events_data:
            df = pd.DataFrame(events_data)
            # 增加展示列
            if 'start' not in df.columns: df['start'] = ""
            # 格式化时间显示 (去除T)
            df['ShowTime'] = df['start'].apply(lambda x: str(x).replace('T', ' ')[:-3] if x else '')
            df['Select'] = False # 复选框列
            
            # 数据编辑器
            edited_df = st.data_editor(
                df[['Select', 'ShowTime', 'title']],
                column_config={
                    "Select": st.column_config.CheckboxColumn("删?", default=False, width="small"),
                    "ShowTime": st.column_config.TextColumn("时间", width="medium"),
                    "title": st.column_config.TextColumn("事项", width="medium"),
                },
                hide_index=True,
                use_container_width=True,
                height=300
            )
            
            # 获取被选中的索引
            to_delete_indices = edited_df[edited_df['Select']].index.tolist()
            
            if to_delete_indices:
                if st.button(f"🗑️ 删除选中的 {len(to_delete_indices)} 项", type="primary", use_container_width=True):
                    # 倒序删除避免索引偏移
                    for i in sorted(to_delete_indices, reverse=True):
                        if i < len(events_data):
                            events_data.pop(i)
                    calendar_db.save(events_data, sha_cal, "Batch Delete")
                    st.success("删除成功")
                    st.rerun()
        else:
            st.info("暂无日程")
        st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# Tab 2: 记账系统
# ------------------------------------------
with tab_fin:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    
    # 顶部：对话框输入
    c1, c2 = st.columns([4, 1])
    with c1:
        fin_txt = st.chat_input("💬 记账: 超市买菜60元 / 收到奖金5000")
    
    if fin_txt:
        with st.spinner("💰 入账中..."):
            record = ai_parse_finance(fin_txt)
            if record:
                f_data, f_sha = finance_db.load()
                f_data.append(record)
                finance_db.save(f_data, f_sha)
                st.toast(f"已记录: {record['item']}", icon="✅")
                st.rerun()

    # 中部：数据展示
    f_data, _ = finance_db.load()
    if f_data:
        df_f = pd.DataFrame(f_data)
        df_f['amount'] = pd.to_numeric(df_f['amount'])
        
        # 1. 核心指标
        t1, t2, t3 = st.columns(3)
        income = df_f[df_f['amount'] > 0]['amount'].sum()
        expense = df_f[df_f['amount'] < 0]['amount'].sum()
        balance = income + expense
        
        t1.metric("总资产", f"¥{balance:,.2f}")
        t2.metric("总收入", f"¥{income:,.2f}", delta="Income")
        t3.metric("总支出", f"¥{abs(expense):,.2f}", delta="Expense", delta_color="inverse")
        
        st.divider()
        
        # 2. 图表与明细
        gc1, gc2 = st.columns(2)
        with gc1:
            st.caption("📊 支出分布")
            df_exp = df_f[df_f['amount'] < 0].copy()
            if not df_exp.empty:
                df_exp['abs_val'] = df_exp['amount'].abs()
                fig = px.pie(df_exp, values='abs_val', names='category', hole=0.5,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无支出")
                
        with gc2:
            st.caption("📜 近期账单")
            st.dataframe(
                df_f[['date', 'category', 'item', 'amount']].sort_values('date', ascending=False),
                hide_index=True,
                use_container_width=True,
                height=300,
                column_config={
                    "amount": st.column_config.NumberColumn("金额", format="¥%.2f")
                }
            )
    else:
        st.info("👋 空空如也，试着输入 '打车花了30元' 开始第一笔记账吧！")
    
    st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------
# Tab 3: 灵感胶囊 (备忘)
# ------------------------------------------
with tab_note:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    
    # 输入区
    with st.form("note_form", clear_on_submit=True):
        col_n1, col_n2 = st.columns([5, 1])
        n_content = col_n1.text_input("💡 捕捉灵感...", placeholder="今天有什么新想法？")
        if col_n2.form_submit_button("保存", use_container_width=True):
            if n_content:
                n_data, n_sha = notes_db.load()
                n_data.insert(0, {
                    "content": n_content,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                notes_db.save(n_data, n_sha)
                st.rerun()
    
    # 瀑布流展示
    n_data, n_sha = notes_db.load()
    if n_data:
        st.markdown("---")
        # 双列布局
        cols = st.columns(2)
        for i, note in enumerate(n_data):
            with cols[i % 2]:
                # 渲染便利贴风格
                st.markdown(f"""
                <div style="
                    background: rgba(255,255,255,0.5);
                    border-left: 5px solid #00bcd4;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 15px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                ">
                    <div style="font-size:0.8em; color:#666; margin-bottom:5px;">📅 {note.get('date')}</div>
                    <div style="font-size:1.1em; font-weight:bold; color:#006064;">{note.get('content')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # 删除按钮 (小小的)
                if st.button("✕ 删除", key=f"del_note_{i}"):
                    n_data.pop(i)
                    notes_db.save(n_data, n_sha)
                    st.rerun()
    else:
        st.info("还没有笔记哦")

    st.markdown('</div>', unsafe_allow_html=True)
