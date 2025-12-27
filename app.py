import streamlit as st
import json
import pandas as pd
from github import Github
from openai import OpenAI  # DeepSeek 兼容 OpenAI 的库，所以这里不用变
from datetime import datetime
import plotly.express as px
import re
import streamlit as st

st.write("正在检查 Secrets 配置...") # 打印一条消息证明代码在跑

if "GITHUB_TOKEN" not in st.secrets:
    st.error("❌ 缺少 GITHUB_TOKEN")
else:
    st.success("✅ GITHUB_TOKEN 已检测到")

if "REPO_NAME" not in st.secrets:
    st.error("❌ 缺少 REPO_NAME")
else:
    st.success("✅ REPO_NAME 已检测到")

if "DEEPSEEK_API_KEY" not in st.secrets:
    st.error("❌ 缺少 DEEPSEEK_API_KEY (你是不是用了 OPENAI_API_KEY?)")
else:
    st.success("✅ DEEPSEEK_API_KEY 已检测到")

# 尝试直接赋值，如果有错让它直接爆红，方便看 Traceback
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO_NAME = st.secrets["REPO_NAME"]
DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]

# 关键修改：初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"  # 指向 DeepSeek 的服务器
)

# --- 工具函数：清洗 JSON ---
def clean_json_string(s):
    """
    DeepSeek 有时会返回 ```json ... ``` 格式，需要清洗掉 Markdown 标记
    才能被 json.loads 解析。
    """
    if not s: return ""
    # 去掉 ```json 和 ``` 
    s = re.sub(r"```json\s*", "", s)
    s = re.sub(r"```", "", s)
    return s.strip()

# --- 2. 通用 GitHub 数据管理器 (保持不变) ---
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

calendar_db = DataManager("events.json")
notes_db = DataManager("notes.json")
finance_db = DataManager("finance.json")

# --- 3. AI 智能处理函数 (针对 DeepSeek 优化) ---

def ai_parse_finance(text):
    prompt = f"""
    分析文本: "{text}"
    提取记账信息，只返回纯 JSON 字符串，不要Markdown格式:
    - item: 消费内容
    - amount: 金额 (数字，支出为负，收入为正)
    - category: 类别 (如: 餐饮, 交通, 购物, 工资)
    - date: YYYY-MM-DD (默认今天 {datetime.now().strftime('%Y-%m-%d')})
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",  # 使用 DeepSeek V3
            messages=[
                {"role": "system", "content": "你是一个严谨的数据助理，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        content = clean_json_string(response.choices[0].message.content)
        return json.loads(content)
    except Exception as e:
        st.error(f"解析出错: {e}")
        return None

def ai_parse_calendar(text):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M %A")
    prompt = f"""
    当前时间: {current_time}。
    分析文本: "{text}"，提取日历事件，只返回纯 JSON 字符串:
    - title: 标题
    - date: YYYY-MM-DD
    - time: HH:MM
    - location: 地点
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # 使用 DeepSeek V3
            messages=[
                {"role": "system", "content": "你是一个严谨的日历助理，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        content = clean_json_string(response.choices[0].message.content)
        return json.loads(content)
    except Exception as e:
        st.error(f"解析出错: {e}")
        return None

# --- 4. 界面构建 (保持不变) ---

st.title("🦈 DeepSeek 智能助理")

tab1, tab2, tab3 = st.tabs(["📅 日程管理", "💰 极速记账", "📝 灵感备忘"])

# ================= Tab 1: 日历 =================
with tab1:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("新增日程")
        cal_input = st.text_area("输入计划...", height=100, key="cal_in")
        if st.button("添加日程", key="btn_cal"):
            if cal_input:
                with st.spinner("DeepSeek 正在思考..."):
                    event = ai_parse_calendar(cal_input)
                    if event:
                        data, sha = calendar_db.load()
                        data.insert(0, event)
                        if calendar_db.save(data, sha, "Add event"):
                            st.success("✅ 添加成功")
                            st.rerun()
    with col2:
        st.subheader("日程列表")
        events, _ = calendar_db.load()
        if events:
            df_cal = pd.DataFrame(events)
            st.dataframe(df_cal, column_config={"title": "事件", "date": "日期", "time": "时间", "location": "地点"}, hide_index=True, use_container_width=True)
        else:
            st.info("暂无日程")

# ================= Tab 2: 记账 =================
with tab2:
    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        fin_input = st.text_input("输入消费 (如: 超市买菜60元):", key="fin_in")
    with f_col2:
        if st.button("记一笔", key="btn_fin", type="primary"):
            if fin_input:
                with st.spinner("DeepSeek 正在计算..."):
                    record = ai_parse_finance(fin_input)
                    if record:
                        data, sha = finance_db.load()
                        data.append(record)
                        if finance_db.save(data, sha, "Add finance"):
                            st.success(f"✅ 已记录: {record['item']}")
                            st.rerun()

    fin_data, _ = finance_db.load()
    if fin_data:
        df_fin = pd.DataFrame(fin_data)
        m1, m2, m3 = st.columns(3)
        m1.metric("当前结余", f"¥{df_fin['amount'].sum():.2f}")
        m2.metric("总支出", f"¥{abs(df_fin[df_fin['amount'] < 0]['amount'].sum()):.2f}")
        m3.metric("笔数", len(df_fin))
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("支出构成")
            df_exp = df_fin[df_fin['amount'] < 0].copy()
            if not df_exp.empty:
                df_exp['abs'] = df_exp['amount'].abs()
                st.plotly_chart(px.pie(df_exp, values='abs', names='category', hole=0.4), use_container_width=True)
        with c2:
            st.dataframe(df_fin[['date', 'item', 'amount', 'category']].sort_values('date', ascending=False), hide_index=True)

# ================= Tab 3: 备忘 =================
with tab3:
    st.subheader("随手记")
    with st.form("note"):
        content = st.text_area("内容")
        tags = st.text_input("标签")
        if st.form_submit_button("保存"):
            if content:
                new_note = {"content": content, "tags": tags.split(), "created_at": datetime.now().strftime("%Y-%m-%d")}
                data, sha = notes_db.load()
                data.insert(0, new_note)
                if notes_db.save(data, sha, "Add note"):
                    st.rerun()
    
    st.divider()
    notes, _ = notes_db.load()
    for n in notes:
        st.info(f"📅 {n['created_at']} | {n['content']} \n\n {' '.join(['#'+t for t in n.get('tags',[])])}")
