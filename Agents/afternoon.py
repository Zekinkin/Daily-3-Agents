# 环境配置
import os, feedparser, smtplib, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from openai import OpenAI
from dotenv import load_dotenv
import time
import json
import random
from services.sheets import push_to_sheets
import datetime
from datetime import timedelta, timezone

load_dotenv() # 加载你的 .env 文件
print("环境配置已加载")

# ================= 🇨🇳 北京时间智能日期逻辑 (新增) =================
# 1. 强制创建一个北京时区 (UTC+8)
beijing_tz = timezone(timedelta(hours=8))

# 2. 获取当前的北京时间
now_in_beijing = datetime.datetime.now(beijing_tz)

# 3. 核心判断逻辑：
# 如果北京时间超过 18:00 (晚上6点)，系统认为这是在"为明天备稿" -> 日期 +1
# 如果北京时间没到 18:00 (比如上午补发)，系统认为这是"当日急救" -> 日期不变
if now_in_beijing.hour >= 18:
    target_date = now_in_beijing.date() + timedelta(days=1)
else:
    target_date = now_in_beijing.date()

# 生成两种格式供下面使用
today_str = target_date.strftime("%Y-%m-%d")  # 格式：2026-01-20
display_date_str = target_date.strftime('%A, %B %d, %Y') # 格式：Tuesday, January 20, 2026
# ================================================================

BASE_DIR = os.getcwd()

DB_PATH = os.path.join(BASE_DIR, "IELTS Speaking Materials", "Speaking_Materials.json")

# 状态记录文件 (还是放在根目录)
STATE_FILE = os.path.join(BASE_DIR, "ielts_state.json")

# 状态记录文件 (自动生成，用来记进度)
STATE_FILE = "ielts_state.json" 

# 初始化 DeepSeek
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 读取数据 & 管理数据
def get_daily_topic(force_topic_id=None):
    """
    负责获取话题。
    :param force_topic_id: (可选) 传入数字 ID，强制从该话题开始（例如 1 表示从头开始）。
    """
    # 1. 加载题库
    if not os.path.exists(DB_PATH):
        print("❌ 找不到题库文件！请检查路径。")
        return None, None
    
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        full_db = json.load(f)
        total_topics = len(full_db)

    # 2. 确定今天的 Index (0-based)
    if force_topic_id is not None:
        # 【情况 A：用户指定了话题】
        # 用户输入 1，我们要转成列表索引 0
        current_index = force_topic_id - 1
        print(f"🔧 [手动模式] 强制跳转到话题 ID: {force_topic_id}")
    else:
        # 【情况 B：正常读取进度】
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                current_index = state.get('current_index', 0)
        else:
            current_index = 0

    # 3. 处理循环逻辑 (核心需求)
    # 如果进度跑到了 50 (而总数只有 50)，说明该回到 0 了
    if current_index >= total_topics:
        print("🔁 恭喜！所有话题已完成一轮。进度自动重置，从头开始。")
        current_index = 0
    
    # 4. 获取话题数据
    # 双重保险：防止 force_topic_id 输入过大报错
    safe_index = current_index % total_topics 
    topic_data = full_db[safe_index]
    
    # 5. 随机抽取 P3
    all_p3 = topic_data.get('part3_questions', [])
    if len(all_p3) > 3:
        selected_p3 = random.sample(all_p3, 3)
    else:
        selected_p3 = all_p3

    # 6. 更新并保存进度 (指向明天要发的下一个)
    # 明天就是 current_index + 1
    next_index = safe_index + 1
    
    new_state = {
        'current_index': next_index, 
        'last_updated': str(today_str),
        'last_topic_name': topic_data['topic_name'] # 顺便记一下上次发了啥，方便人工检查
    }
    
    with open(STATE_FILE, 'w') as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)
        
    print(f"✅ 今日锁定话题: [ID {topic_data['id']}] {topic_data['topic_name']}")
    print(f"📅 明日预定进度: Index {next_index} (ID {next_index + 1})")
    
    return topic_data, selected_p3


# generate_ielts_html
def generate_ielts_html(topic_data, selected_p3):
    print("🧠 正在调用 DeepSeek 生成口语逻辑简报 (Sage Green 2.0)...")
    
    # 准备 Prompt 素材
    p3_text_list = "\n".join([f"- {q}" for q in selected_p3])
    
    # --- 1. System Prompt: 强化 HTML 格式指令 ---
    system_prompt = """
    你是一位雅思口语专家（Band 9）。
    你的任务是根据提供的话题素材，生成一份 HTML 格式的口语逻辑训练简报。
    你的教学目标是：拒绝平庸的模板，教会学生如何用“逻辑+地道词伙”征服考官。
    
    你的输出风格：
    1. **结构清晰**：使用 HTML 格式。
    2. **逻辑硬核**：在 Logic 部分，必须给出 Pros/Cons 或 Macro/Micro 的深度分析。
    3. **词汇高级**：只讲 Collocations（词伙），不讲简单单词，并且至少给出10个以上Collocations。
    
    ⚠️ 【极其重要的格式指令】：
    1. **绝对禁止**使用 Markdown 语法（如 **bold**）。
    2. **必须使用** HTML 标签来设置样式（如 <b>bold</b>, <u>underline</u>）。
    3. 你的输出必须是纯粹的 HTML 代码，不要包含 ```html 包裹符。
    """
    
    # --- 2. User Prompt: 分离数据与模板 ---
    user_prompt = f"""
    【今日素材】：
    Topic: {topic_data['topic_name']}
    
    [Part 2 Cue Card 原文]:
    {topic_data['part2_content']}
    
    [Part 3 Selected Questions]:
    {p3_text_list}
    
    【任务目标】：
    请将上述素材填入下方的 HTML 模板中，并根据要求进行改写和扩充。
    
    【排版与内容要求】：
    1. **Part 2 部分**：不要直接复制原文！请把题目第一句话加粗，剩下的 "You should say" 部分拆解成一个 HTML 列表 (ul/li)。
    2. **Critical Thinking 部分**：不要给一大段中文。请生成 5-6 组【逻辑解析 + 英文表达】的对照。
       - 英文部分必须使用高分词汇，**难词用 <u>下划线</u> 标记**，并在其后紧跟 **【中文释义】**。
    3. **Sample Answer**：针对第一个 P3 问题写一个示范回答。
    
    【HTML 模板代码 (请严格套用)】：
    
    <div style="background-color: #f0f7f4; padding: 20px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333;">
        
        <div style="max-width: 600px; margin: 0 auto; margin-bottom: 30px; text-align: center; border-bottom: 3px solid #57a086; padding-bottom: 15px;">
            <h1 style="color: #2d6a4f; font-size: 28px; margin-bottom: 5px; font-weight: 800;">IELTS Speaking Booster</h1>
            <p style="color: #52b788; font-size: 14px; font-weight: bold; background-color: #d8f3dc; display: inline-block; padding: 4px 12px; border-radius: 15px;">
                Topic: {topic_data['topic_name']}
            </p>
        </div>

        <div style="max-width: 600px; margin: 0 auto;">

            <div style="background-color: white; border-radius: 10px; padding: 20px; margin-bottom: 25px; box-shadow: 0 4px 10px rgba(87, 160, 134, 0.15);">
                <h3 style="color: #2d6a4f; margin-top: 0; border-left: 5px solid #57a086; padding-left: 10px; font-size: 18px;">🎯 Topic Overview</h3>
                
                <div style="font-size: 15px; color: #333; margin-bottom: 20px; background-color: #f9fdfa; padding: 15px; border-radius: 8px; border: 1px solid #e0f2e9;">
                    <div style="color: #2d6a4f; font-weight: bold; margin-bottom: 10px;">
                        (请在这里填入 Part 2 的主标题，例如: Describe a friend...)
                    </div>
                    <ul style="color: #555; margin: 0; padding-left: 20px; line-height: 1.6;">
                        <li>You should say: who he/she is</li>
                        <li>(要点 2...)</li>
                        <li>(要点 3...)</li>
                    </ul>
                </div>

                <div style="font-size: 14px; color: #555;">
                    <b>Selected P3 Questions:</b><br>
                    {p3_text_list.replace(chr(10), '<br>')}
                </div>
            </div>

            <div style="background-color: white; border-radius: 10px; padding: 20px; margin-bottom: 25px; box-shadow: 0 4px 10px rgba(87, 160, 134, 0.15);">
                <h3 style="color: #2d6a4f; margin-top: 0; border-left: 5px solid #57a086; padding-left: 10px; font-size: 18px;">💎 Band 9 Lexical Resource</h3>
                <p style="font-size: 14px; color: #666; margin-bottom: 15px;">Use these <b>Collocations</b> to sound native.</p>
                <ul style="line-height: 1.8; color: #333; padding-left: 20px;">
                    <li style="margin-bottom: 10px;">
                        <span style="color: #2d6a4f; font-weight: bold; background-color: #d8f3dc; padding: 2px 6px; border-radius: 4px;">Collocations (English)</span>
                        <span style="font-size: 14px;"> : 中文含义（ 这里给出英文简短例句或用法示意）</span> 
                    </li>
                </ul>
            </div>

            <div style="background-color: white; border-radius: 10px; padding: 20px; margin-bottom: 25px; box-shadow: 0 4px 10px rgba(87, 160, 134, 0.15);">
                <h3 style="color: #2d6a4f; margin-top: 0; border-left: 5px solid #57a086; padding-left: 10px; font-size: 18px;">🧠 Critical Thinking</h3>
                <p style="font-size: 14px; color: #888; margin-bottom: 15px;">Deep analysis for the topic.</p>
                
                <div style="margin-bottom: 20px;">
                    <div style="font-size: 15px; color: #333; margin-bottom: 8px; font-weight: bold;">
                        💡 思维角度：(例如：个人层面 vs 社会层面)
                    </div>
                    <div style="font-size: 14px; color: #444; margin-bottom: 8px; line-height: 1.6;">
                        (这里写中文逻辑分析，解释为什么...)
                    </div>
                    <div style="background-color: #f0f7f4; padding: 10px; border-radius: 6px; color: #2d6a4f; font-size: 14px; line-height: 1.6; border-left: 3px solid #57a086;">
                        🔤 <b>Express it:</b> <br>
                        (这里写对应的英文表达句子，必须包含 <u>difficult words</u>【中文】)
                    </div>
                </div>

                </div>

            <div style="background-color: #ebfcf0; border: 2px dashed #57a086; border-radius: 10px; padding: 20px; position: relative;">
                <div style="position: absolute; top: -12px; left: 20px; background-color: #2d6a4f; color: white; padding: 2px 10px; font-size: 12px; border-radius: 4px;">Part 3 Sample Answer</div>
                
                <div style="margin-top: 15px; font-weight: bold; color: #2d6a4f; font-size: 16px;">
                    Q: {selected_p3[0]}
                </div>
                
                <div style="margin-top: 10px; font-size: 16px; color: #333; line-height: 1.8;">
                   (请生成回答，重点词汇使用 <b>bold</b>【中文】 或 <u>underline</u>【中文】)
                </div>
                
                <div style="margin-top: 15px; border-top: 1px solid #b7e4c7; padding-top: 10px; font-size: 13px; color: #52b788;">
                    💡 <b>Examiner's Note:</b> (简短点评)
                </div>
            </div>

            <div style="text-align: center; margin-top: 40px; color: #57a086; font-size: 12px; font-style: italic;">
                Daily Progress · {target_date.strftime('%Y.%m.%d')}
            </div>

        </div> 
    </div>
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        return None
    

# run
def run():
    print("☀️ 午报 Agent 启动...")
    result = get_daily_topic()
    
    if result:
        topic_data, selected_p3 = result
        html_content = generate_ielts_html(topic_data, selected_p3)
        
        if html_content:

            # 推送到 Google Sheets
            subject = f"Afternoon Brief: {today_str}"
            push_to_sheets("afternoon", subject, html_content)
            print("😏已push到Google Sheet")

            return html_content
