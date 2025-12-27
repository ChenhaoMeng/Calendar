import streamlit as st
import json
import pandas as pd
from github import Github, Auth
from openai import OpenAI
from datetime import datetime
import re
from streamlit_calendar import calendar

# --- 1. 基础配置 (必须在第一行) ---
st.set_page_config(
    page_title="DeepSeek Life OS",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. CSS 深度美化 (毛玻璃 + 水蓝系) ---
st.markdown("""
<style>
    /* 全局背景：水蓝渐变 */
    .stApp {
        background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 50%, #80deea 100%);
        background-attachment: fixed;
    }

    /* 侧边栏毛玻璃 */
    section[data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.4);
        backdrop-filter: blur(12px);
        border-right: 1px solid rgba(255, 255, 255, 0.5);
    }

    /* 顶部标题栏隐藏/透明化 */
    header {
        background: transparent !important;
    }

    /* 通用卡片：毛玻璃效果 */
    .glass-card {
        background: rgba(255, 255, 255, 0.55);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.6);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
        padding: 24px;
        margin-bottom: 20px;
        color: #006064; /* 深青色文字 */
    }

    /* 输入框美化 */
    .stTextArea textarea, .stTextInput input {
        background-color: rgba(255, 255, 255, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.8) !important;
        border-radius: 12px !important;
        color: #006064 !important;
    }
    
    /* 按钮美化 - 水蓝风格 */
    div.stButton > button {
        background: linear-gradient(45deg, #4dd0e1, #00bcd4);
        color: white;
        border: none;
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0, 188, 212, 0.3);
        transition: all 0.3s ease;
        font-weight: bold;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 188, 212, 0.4);
        background: linear-gradient(45deg, #26c6da, #00acc1);
    }
    
    /* 删除按钮特别样式 (红色系微调) */
    .delete-btn button {
        background: rgba(255, 82, 82, 0.1) !important;
        color: #ff5252 !important;
        border: 1px solid rgba(255, 82, 82, 0.3) !important;
        box-shadow: none !important;
    }
    .delete-btn button:hover {
        background: #ff5252 !important;
        color: white !important;
    }

    /* 字体颜色覆盖 */
    h1, h2, h3, h4, p, label {
        color: #006064 !important;
        font-family: 'Helvetica Neue', sans-serif;
    }
    
    /* Expander 样式 */
    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.5);
        border-radius: 10px;
        color: #006064;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 初始化与连接 ---
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    st.error("❌ 配置丢失，请检查 Secrets")
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

# --- 4. 数据管理类 ---
class DataManager:
    def __init__(self, filename):
        self.filename = filename
        self.repo = get_repo()

    def load(self):
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

calendar_db = DataManager("events.json")

# --- 5. AI 解析逻辑 (24小时制强化) ---
def clean_json(s):
    s = re.sub(r"```json\s*", "", s)
    s = re.sub(r"```", "", s)
    return s.strip()

def ai_parse_calendar(text):
    prompt = f"""
    当前年份: {datetime.now().year}。
    分析文本: "{text}"
    请提取日程并返回JSON**数组** (List)。
    要求:
    1. start/end 必须是 ISO 格式: "YYYY-MM-DDTHH:MM:SS" (严格24小时制, 如 13:30)。
    2. 如果文本中有类似 (13:10-15:10) 的时间段，必须拆分为 start 和 end。
    3. title: 事件名称。
    4. location: 地点。
    5. allDay: 如果有具体时间则为 false，否则 true。
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        res = json.loads(clean_json(response.choices[0].message.content))
        return res if isinstance(res, list) else [res]
    except:
        return []

# --- 6. 主逻辑 ---
st.title("🌊 DeepSeek Flow")

# 容器：毛玻璃卡片包裹日历区域
with st.container():
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    
    col_main, col_list = st.columns([7, 3])

    # === 左侧：日历视图 ===
    with col_main:
        st.subheader("📅 日程概览")
        events_data, sha = calendar_db.load()
        
        # 转换数据给日历组件
        cal_events = []
        for e in events_data:
            cal_events.append({
                "title": f"{e.get('title')}",
                "start": e.get('start'),
                "end": e.get('end'),
                "color": "#00bcd4", # 水蓝色块
                "textColor": "#ffffff"
            })
            
        calendar_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,listWeek"
            },
            "initialView": "dayGridMonth",
            "height": 600,
            "slotMinTime": "06:00:00",
            "slotMaxTime": "23:00:00"
        }
        calendar(events=cal_events, options=calendar_options, key="flow_cal")

    # === 右侧：控制台 (添加 & 列表 & 删除) ===
    with col_list:
        # 1. 添加功能 (折叠面板)
        with st.expander("✨ 添加日程 (点击展开)", expanded=False):
            with st.form("add_form", clear_on_submit=True):
                txt = st.text_area("粘贴课表或输入安排...", height=100, 
                                 placeholder="2025-01-16 13:10 语音学 东下院102...")
                if st.form_submit_button("🚀 智能解析", type="primary", use_container_width=True):
                    if txt:
                        with st.spinner("正在分析时间..."):
                            new_items = ai_parse_calendar(txt)
                            if new_items:
                                # --- 核心逻辑：去重 ---
                                existing_keys = {f"{e.get('start')}_{e.get('title')}" for e in events_data}
                                unique_adds = []
                                for item in new_items:
                                    key = f"{item.get('start')}_{item.get('title')}"
                                    if key not in existing_keys:
                                        unique_adds.append(item)
                                        existing_keys.add(key) # 防止本次批量中也有重复
                                
                                if unique_adds:
                                    events_data.extend(unique_adds)
                                    if calendar_db.save(events_data, sha):
                                        st.toast(f"已添加 {len(unique_adds)} 条日程 (已去重)", icon="✅")
                                        st.rerun()
                                else:
                                    st.warning("所有日程均已存在，跳过重复项。")
                            else:
                                st.error("无法解析内容")

        st.markdown("---")
        
        # 2. 列表与删除功能
        st.subheader("📋 待办清单")
        
        if not events_data:
            st.info("暂无安排，享受自由时光~ 🍵")
        else:
            # 按时间排序
            events_data.sort(key=lambda x: x.get('start', ''))
            
            # 限制显示高度，避免太长
            with st.container(height=500):
                for i, event in enumerate(events_data):
                    # 解析时间用于显示
                    start_raw = event.get('start', '')
                    try:
                        dt = datetime.fromisoformat(start_raw)
                        time_display = dt.strftime("%m-%d %H:%M") # 24小时制显示
                    except:
                        time_display = start_raw

                    # 单行布局：内容 + 删除按钮
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"""
                        <div style="background:rgba(255,255,255,0.4);padding:8px;border-radius:8px;margin-bottom:5px;">
                            <div style="font-weight:bold;font-size:0.9em;">{event.get('title')}</div>
                            <div style="font-size:0.8em;color:#666;">🕐 {time_display} 📍 {event.get('location','')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with c2:
                        # 删除按钮
                        st.markdown('<div class="delete-btn">', unsafe_allow_html=True)
                        if st.button("✕", key=f"del_{i}", help="删除此日程"):
                            events_data.pop(i)
                            calendar_db.save(events_data, sha, "Delete event")
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True) # End glass-card
