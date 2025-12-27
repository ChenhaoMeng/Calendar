import streamlit as st
import json
import pandas as pd
from github import Github, Auth
from openai import OpenAI
from datetime import datetime
import re
from streamlit_calendar import calendar

# --- 1. 基础配置 ---
st.set_page_config(
    page_title="DeepSeek Life OS",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. 强力 CSS 注入 (修复样式失效问题) ---
# 注意：这里使用了 data-testid 来更精准地定位元素，并配合 !important 强制覆盖主题
st.markdown("""
<style>
    /* 1. 强制覆盖全局背景 (无论深色/浅色模式) */
    .stApp {
        background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 50%, #80deea 100%) !important;
        background-attachment: fixed !important;
    }

    /* 2. 侧边栏样式 */
    section[data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.4) !important;
        backdrop-filter: blur(12px);
        border-right: 1px solid rgba(255, 255, 255, 0.5);
    }
    
    /* 3. 字体颜色强制修正 (防止在深色模式下变成白色看不清) */
    h1, h2, h3, p, div, span, label {
        color: #006064 !important; /* 深青色 */
        text-shadow: none !important;
    }
    
    /* 4. 毛玻璃卡片容器 */
    .glass-container {
        background: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.8);
        padding: 25px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
        margin-bottom: 20px;
    }

    /* 5. 按钮美化 */
    div.stButton > button {
        background: linear-gradient(45deg, #26c6da, #00acc1) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: bold !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
        transition: transform 0.1s;
    }
    div.stButton > button:active {
        transform: scale(0.98);
    }
    
    /* 6. 输入框背景修正 */
    .stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: rgba(255, 255, 255, 0.7) !important;
        color: #004d40 !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255, 255, 255, 1) !important;
    }
    
    /* 7. 表格样式 (用于删除面板) */
    div[data-testid="stDataEditor"] {
        background-color: rgba(255, 255, 255, 0.5);
        border-radius: 10px;
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 初始化连接 ---
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
except:
    st.error("❌ Secrets 配置丢失")
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
    def __init__(self, filename):
        self.filename = filename
        self.repo = get_repo()

    def load(self):
        try:
            contents = self.repo.get_contents(self.filename)
            sha = contents.sha
            data = json.loads(contents.decoded_content.decode())
            if not isinstance(data, list): data = []
            return data, sha
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
            st.error(f"Save failed: {e}")
            return False

calendar_db = DataManager("events.json")

# --- 4. AI 逻辑 ---
def clean_json(s):
    s = re.sub(r"```json\s*", "", s)
    s = re.sub(r"```", "", s)
    return s.strip()

def ai_parse_calendar(text):
    prompt = f"""
    当前年份: {datetime.now().year}。
    分析文本: "{text}"
    提取日程并返回JSON数组。
    规则:
    1. start/end 必须是 ISO 格式 "YYYY-MM-DDTHH:MM:SS" (24小时制)。
    2. 如果有时间段 (如 13:00-15:00)，分别写入 start 和 end。
    3. title: 事件名。
    4. location: 地点。
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

# --- 5. 页面逻辑 ---
st.title("🌊 DeepSeek Life OS")

# 加载数据
events_data, sha = calendar_db.load()

# === 主布局 ===
col_left, col_right = st.columns([2, 1])

# 左侧：日历视图
with col_left:
    st.markdown('<div class="glass-container">', unsafe_allow_html=True)
    st.subheader("📅 日程视图")
    
    cal_events = []
    for e in events_data:
        cal_events.append({
            "title": e.get('title'),
            "start": e.get('start'),
            "end": e.get('end'),
            "color": "#00acc1",
            "textColor": "#ffffff"
        })
        
    calendar_options = {
        "headerToolbar": {"left": "title", "center": "", "right": "dayGridMonth,timeGridWeek,listWeek"},
        "initialView": "dayGridMonth",
        "height": 650,
        "slotMinTime": "06:00:00",
        "slotMaxTime": "24:00:00"
    }
    calendar(events=cal_events, options=calendar_options, key="main_cal")
    st.markdown('</div>', unsafe_allow_html=True)

# 右侧：操作面板 + 批量管理
with col_right:
    # --- 1. 添加面板 ---
    st.markdown('<div class="glass-container">', unsafe_allow_html=True)
    st.subheader("✨ 智能添加")
    with st.form("add_form", clear_on_submit=True):
        txt = st.text_area("输入...", height=80, placeholder="粘贴文本或输入：明天下午三点开会")
        if st.form_submit_button("解析并去重导入", use_container_width=True):
            if txt:
                with st.spinner("Processing..."):
                    new_items = ai_parse_calendar(txt)
                    if new_items:
                        # 去重逻辑
                        existing_keys = {f"{e.get('start')}_{e.get('title')}" for e in events_data}
                        added_count = 0
                        for item in new_items:
                            key = f"{item.get('start')}_{item.get('title')}"
                            if key not in existing_keys:
                                events_data.append(item)
                                existing_keys.add(key)
                                added_count += 1
                        
                        if added_count > 0:
                            calendar_db.save(events_data, sha, "Add events")
                            st.toast(f"成功添加 {added_count} 条日程", icon="🎉")
                            st.rerun()
                        else:
                            st.warning("所有日程已存在，无需添加")
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 2. 批量管理面板 (删除功能升级) ---
    st.markdown('<div class="glass-container">', unsafe_allow_html=True)
    st.subheader("🗑️ 批量管理")
    
    if events_data:
        # 将 JSON 转换为 DataFrame 方便展示
        df = pd.DataFrame(events_data)
        
        # 只需要展示这几列
        cols_to_show = ['start', 'title', 'location']
        # 确保列存在，防止报错
        for c in cols_to_show:
            if c not in df.columns: df[c] = ""
            
        # 格式化时间列显示，去掉T，只保留好看的格式
        df['display_time'] = df['start'].apply(lambda x: x.replace('T', ' ')[:-3] if x else '')
        
        # 使用 data_editor 增加一个 "删除?" 勾选列
        df['删除'] = False 
        
        edited_df = st.data_editor(
            df[['删除', 'display_time', 'title', 'location']],
            column_config={
                "删除": st.column_config.CheckboxColumn("选中删除", default=False),
                "display_time": "时间",
                "title": "事项",
                "location": "地点"
            },
            hide_index=True,
            use_container_width=True,
            height=300
        )
        
        # 执行删除逻辑
        # 只有当用户勾选并点击下面的按钮时才触发
        delete_indices = edited_df[edited_df['删除']].index.tolist()
        
        if delete_indices:
            st.warning(f"已选中 {len(delete_indices)} 条日程")
            if st.button("🔴 确认删除选中的日程", use_container_width=True):
                # 倒序删除，防止索引错位
                for i in sorted(delete_indices, reverse=True):
                    if i < len(events_data):
                        events_data.pop(i)
                
                calendar_db.save(events_data, sha, "Batch delete")
                st.success("删除成功！")
                st.rerun()
    else:
        st.info("暂无数据")
        
    st.markdown('</div>', unsafe_allow_html=True)
