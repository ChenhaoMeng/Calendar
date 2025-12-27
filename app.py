import streamlit as st
import json
import pandas as pd
from github import Github
from openai import OpenAI
from datetime import datetime
import plotly.express as px

# --- 1. 配置与初始化 ---
st.set_page_config(page_title="AI 全能助理", page_icon="🤖", layout="wide")

# 获取 Secrets (从 Streamlit Cloud 环境变量中读取)
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    REPO_NAME = st.secrets["REPO_NAME"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
except:
    st.error("请在 Streamlit Cloud 的 Settings -> Secrets 中配置 API Key 和 Token")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# --- 2. 通用 GitHub 数据管理器 ---
class DataManager:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.g = Github(GITHUB_TOKEN)
            self.repo = self.g.get_repo(REPO_NAME)
        except Exception as e:
            st.error(f"GitHub 连接失败: {e}")

    def load(self):
        """读取数据"""
        try:
            contents = self.repo.get_contents(self.filename)
            return json.loads(contents.decoded_content.decode()), contents.sha
        except:
            return [], None

    def save(self, new_data_list, sha, commit_msg="Update data"):
        """保存数据"""
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

# 初始化三个管理器
calendar_db = DataManager("events.json")
notes_db = DataManager("notes.json")
finance_db = DataManager("finance.json")

# --- 3. AI 智能处理函数 ---

def ai_parse_finance(text):
    """记账专用 AI"""
    prompt = f"""
    分析文本: "{text}"
    提取记账信息，返回 JSON:
    - item: 消费内容 (如: 午餐)
    - amount: 金额 (数字，负数表示支出，正数表示收入。默认是支出，请转为负数)
    - category: 类别 (如: 餐饮, 交通, 购物, 工资)
    - date: YYYY-MM-DD (默认今天 {datetime.now().strftime('%Y-%m-%d')})
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except:
        return None

def ai_parse_calendar(text):
    """日历专用 AI"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    prompt = f"""
    当前时间: {current_time}。
    分析文本: "{text}"，提取日历事件 JSON:
    - title: 标题
    - date: YYYY-MM-DD
    - time: HH:MM
    - location: 地点
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except:
        return None

# --- 4. 界面构建 ---

st.title("🤖 我的 AI 第二大脑")

# 使用 Tabs 分割三个功能
tab1, tab2, tab3 = st.tabs(["📅 日程管理", "💰 极速记账", "📝 灵感备忘"])

# ================= Tab 1: 日历功能 =================
with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("新增日程")
        cal_input = st.text_area("输入计划...", height=100, key="cal_in")
        if st.button("添加日程", key="btn_cal"):
            if not cal_input:
                st.warning("请先输入内容")
            else:
                with st.spinner("AI 正在解析..."):
                    event = ai_parse_calendar(cal_input)
                    if event:
                        data, sha = calendar_db.load()
                        data.insert(0, event)
                        if calendar_db.save(data, sha, "Add event"):
                            st.success("已添加到日历！")
                            st.rerun()
                    else:
                        st.error("AI 解析失败，请重试")

    with col2:
        st.subheader("即将到来")
        events, _ = calendar_db.load()
        if events:
            df_cal = pd.DataFrame(events)
            st.dataframe(
                df_cal,
                column_config={
                    "title": "事件",
                    "date": "日期",
                    "time": "时间",
                    "location": "地点"
                },
                hide_index=True, 
                use_container_width=True
            )
        else:
            st.info("暂无日程")

# ================= Tab 2: 记账功能 =================
with tab2:
    st.caption("支持自然语言，例如：'刚才打车花了35元' 或 '发工资10000元'")
    
    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        fin_input = st.text_input("输入消费/收入情况:", key="fin_in")
    with f_col2:
        if st.button("记一笔", key="btn_fin", type="primary"):
            if fin_input:
                with st.spinner("正在计算..."):
                    record = ai_parse_finance(fin_input)
                    if record:
                        data, sha = finance_db.load()
                        data.append(record)
                        if finance_db.save(data, sha, "Add finance record"):
                            st.success(f"已记录: {record['item']}")
                            st.rerun()
                    else:
                        st.error("AI 解析失败")

    fin_data, _ = finance_db.load()
    if fin_data:
        df_fin = pd.DataFrame(fin_data)
        
        # 统计
        total_balance = df_fin['amount'].sum()
        total_expense = df_fin[df_fin['amount'] < 0]['amount'].sum()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("当前结余", f"¥{total_balance:.2f}")
        m2.metric("总支出", f"¥{abs(total_expense):.2f}")
        m3.metric("记录总数", len(df_fin))
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("支出类别占比")
            df_expense = df_fin[df_fin['amount'] < 0].copy()
            if not df_expense.empty:
                df_expense['abs_amount'] = df_expense['amount'].abs()
                fig = px.pie(df_expense, values='abs_amount', names='category', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("暂无支出数据")
                
        with c2:
            st.subheader("近期明细")
            st.dataframe(df_fin[['date', 'category', 'item', 'amount']].sort_values(by='date', ascending=False), hide_index=True)

# ================= Tab 3: 备忘录功能 =================
with tab3:
    st.subheader("随手记")
    
    with st.form("note_form"):
        note_content = st.text_area("内容", placeholder="记录灵感、笔记、待办...")
        note_tags = st.text_input("标签 (用空格分隔)", placeholder="工作 灵感")
        submitted = st.form_submit_button("保存笔记")
        
        if submitted and note_content:
            new_note = {
                "content": note_content,
                "tags": note_tags.split(),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            data, sha = notes_db.load()
            data.insert(0, new_note)
            if notes_db.save(data, sha, "Add note"):
                st.success("笔记已保存")
                st.rerun()
    
    st.divider()
    
    notes_data, _ = notes_db.load()
    search_term = st.text_input("🔍 搜索笔记", "")
    
    for note in notes_data:
        if search_term and search_term not in note['content']:
            continue
            
        with st.container():
            st.markdown(f"""
            <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px;">
                <small style="color: grey;">📅 {note['created_at']}</small><br>
                <div style="font-size: 16px; margin-top: 5px;">{note['content']}</div>
                <div style="margin-top: 10px;">
                    {' '.join([f'<span style="background-color: #e0e0e0; padding: 2px 8px; border-radius: 4px; font-size: 12px;">#{t}</span>' for t in note.get('tags', [])])}
                </div>
            </div>
            """, unsafe_allow_html=True)
