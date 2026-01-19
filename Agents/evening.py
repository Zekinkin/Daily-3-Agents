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
from newspaper import Article
import requests
import re
from services.sheets import push_to_sheets
import datetime
from datetime import timedelta, timezone

# ================= 🇨🇳 北京时间智能日期逻辑 =================
beijing_tz = timezone(timedelta(hours=8))
now_in_beijing = datetime.datetime.now(beijing_tz)

if now_in_beijing.hour >= 18:
    target_date = now_in_beijing.date() + timedelta(days=1)
else:
    target_date = now_in_beijing.date()

today_str = target_date.strftime("%Y-%m-%d")
display_date_str = target_date.strftime('%A, %B %d, %Y')
# =========================================================

# 历史记录文件 (防止发重复的)
BASE_DIR = os.getcwd()
# ⚠️ 注意：这是一个新文件名，GitHub 会自动创建它，不要指向你的素材源文件！
HISTORY_FILE = os.path.join(BASE_DIR, "evening_history.json")

# 字数限制 (单位：英文单词)
MIN_WORDS = 600
MAX_WORDS = 3000

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# rss信息源
SAFE_RSS_SOURCES = [
    # --- 🌌 宇宙与深空 (NASA & Webb) ---
    # NASA 官方新闻：最权威的宇宙探索
    "https://www.nasa.gov/news-release/feed/",
    # 韦伯望远镜 (Webb)：探索宇宙起源，图片和文字都极美
    "https://webbtelescope.org/news/news-releases?format=rss",
    # 钱德拉 X 射线天文台：探索黑洞和超新星
    "https://chandra.si.edu/press/rss.xml",

    # --- 🌿 地球与自然 (USGS & FWS) ---
    # 美国地质调查局 (USGS)：关于火山、地震、矿物、地质奇观
    "https://www.usgs.gov/news/feed",
    # 美国鱼类及野生动物管理局 (FWS)：保护濒危动物、湿地故事
    "https://www.fws.gov/news/rss",
    
    # --- 🧬 基础科学 (NSF) ---
    # 美国国家科学基金会 (NSF)：前沿科学发现（生物、物理、极地探索）
    "https://www.nsf.gov/rss/rss_www_news.xml",
    
    # --- ☁️ 大气与海洋 (NOAA) ---
    # 美国国家海洋和大气管理局 (NOAA)：海洋深处、气候、极光
    "https://www.noaa.gov/news-releases/feed"
]


# 违禁词库
BANNED_KEYWORDS = [
    # Politics & Geopolitics
    "trump", "biden", "election", "democrat", "republican", "senate", "congress",
    "white house", "putin", "xi jinping", "zelensky", "netanyahu",
    "ukraine", "russia", "gaza", "israel", "palestine", "hamas", "war", "military",
    "strike", "missile", "weapon", "sanction", "treaty", "diplomacy",
    "government", "politics", "policy", "parliament", "protest", "riot",
    
    # Crime & Violence
    "murder", "kill", "suicide", "assassinate", "terrorist", "terrorism",
    "bomb", "attack", "shooting", "gun", "crime", "victim", "abuse",
    
    # NSFW / Drugs / Gambling
    "sex", "porn", "erotic", "nude", "rape", "assault",
    "drug", "cocaine", "heroin", "marijuana", "cannabis", "opioid",
    "casino", "gambling", "betting", "lottery"
]


# 获取文章 
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_history(url):
    history = load_history()
    history.add(url)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(list(history), f)

def is_content_safe(title, text):
    """
    🛡️ 安全过滤器
    检查标题和正文中是否包含违禁词。
    返回: True (安全), False (不安全)
    """
    # 将文本转为小写以便匹配
    content_blob = (title + " " + text).lower()
    
    for keyword in BANNED_KEYWORDS:
        # 使用正则进行单词边界匹配，防止误伤 (例如 banned 'sex' 不应该匹配 'essex')
        # \b 匹配单词边界
        if re.search(r'\b' + re.escape(keyword) + r'\b', content_blob):
            print(f"    ⚠️ 触发敏感词拦截: [{keyword}]")
            return False
            
    return True

def get_filtered_article():
    print("🌙 正在全网搜寻今晚的宇宙与自然 (含安全审查)...")
    
    sent_urls = load_history()
    shuffled_sources = random.sample(SAFE_RSS_SOURCES, len(SAFE_RSS_SOURCES))
    
    for url in shuffled_sources:
        try:
            print(f"  - 正在扫描源: {url} ...")
            feed = feedparser.parse(url)
            if not feed.entries: continue
            
            # 每个源只看前 3 篇，避免浪费时间
            for entry in feed.entries[:3]:
                link = entry.link
                title = entry.title
                
                # 1. 历史查重
                if link in sent_urls: continue
                
                # 2. 标题初步审查 (省流量)
                if not is_content_safe(title, ""):
                    print(f"    ❌ 标题包含敏感词，跳过: {title}")
                    continue

                try:
                    # 抓取全文
                    article = Article(link)
                    article.download()
                    article.parse()
                    text = article.text
                    word_count = len(text.split())
                    
                    # 3. 字数检查
                    if word_count < MIN_WORDS or word_count > MAX_WORDS:
                        # print(f"    ⚠️ 字数不符 ({word_count}): {title}")
                        continue
                    
                    # 4. 全文深度审查 (Deep Check)
                    if not is_content_safe(title, text):
                        print(f"    ❌ 正文包含敏感词，跳过: {title}")
                        continue
                        
                    # ✅ 完美通过
                    print(f"    ✅ 选中文章 ({word_count}词): {title}")
                    return {
                        "title": article.title,
                        "author": entry.get("author", "Unknown"),
                        "source_name": feed.feed.get("title", "Science/Nature Source"),
                        "link": link,
                        "content": text
                    }
                    
                except Exception as e:
                    continue
                    
        except Exception:
            continue
            
    print("😭 未找到合适文章。")
    return None


# generate_evening_html
def generate_evening_html(article_data):
    print("🕯️ DeepSeek 正在为你拆解文章，准备伴读 (注读版)...")
    
    # --- System Prompt ---
    system_prompt = """
    你是一位温暖、博学的“晚间阅读伴侣”。
    你的任务是将一篇英文文章转化为“注读版”网页，供用户睡前阅读。
    
    【排版核心指令】：
    1. **绝对禁止 Markdown**。必须输出纯 HTML 代码。
    2. **视觉风格**：莫兰迪暖咖色 (#fdfbf7)，字体强制使用 Times New Roman。
    3. **结构逻辑**：不要强制分为 Part 1/2/3。请根据文章的自然段落逻辑，将其拆分为若干个“阅读块”（每个块包含 1-2 个自然段）。
    """
    
    # --- User Prompt ---
    user_prompt = f"""
    【文章信息】：
    Title: {article_data['title']}
    Author: {article_data['author']}
    Source: {article_data['source_name']}
    Original Link: {article_data['link']}
    
    【文章内容】：
    {article_data['content']}
    
    【处理要求】：
    请严格按照下方 HTML 模板结构输出完整代码。
    
    1. **正文处理 (Inline Annotations)**：
       - 保持英文原文流畅。
       - 遇到高阶词汇/难词时，**直接在单词后**添加中文释义。
       - 格式要求：使用 `<b>单词</b><span style="color:#bc8a86; font-size: 0.9em;">【中文】</span>`。
       - 例如：The sunset was <b>ephemeral</b><span style="color:#bc8a86; font-size: 0.9em;">【短暂的】</span>...
       
    2. **按需语法卡片 (Conditional Grammar Card)**：
       - 分析当前段落是否存在**长难句**（结构复杂或倒装/虚拟语气等）。
       - **如果有**：在段落下方插入一个“语法解析卡片”，解释该句子的结构。
       - **如果没有**：不要插入卡片，直接继续下一段。
       
    3. **结尾**：
       - 提取一句最治愈的金句 (Golden Quote)。

    【HTML 模板代码 (请循环生成中间的阅读块)】：
    
    <div style="background-color: #fdfbf7; padding: 40px 20px; font-family: 'Times New Roman', Times, serif; color: #2c2c2c; line-height: 2.0;">
        
        <div style="max-width: 650px; margin: 0 auto; text-align: center; margin-bottom: 50px; border-bottom: 1px solid #dcc1be; padding-bottom: 20px;">
            <div style="font-size: 12px; letter-spacing: 2px; color: #bc8a86; text-transform: uppercase; margin-bottom: 10px; font-family: sans-serif;">The Evening Read</div>
            <h1 style="font-size: 32px; color: #5d4037; margin-bottom: 15px; font-weight: normal; font-style: italic;">{article_data['title']}</h1>
            <p style="font-size: 14px; color: #999; font-family: sans-serif;">
                By {article_data['author']}
                <br><a href="{article_data['link']}" style="color: #bc8a86; text-decoration: none;">Read Original Source</a>
            </p>
        </div>

        <div style="max-width: 650px; margin: 0 auto;">
            
            <div style="margin-bottom: 35px;">
                
                <p style="font-size: 19px; text-align: justify; margin-bottom: 15px;">
                    (这里填入原文段落... 遇到难词请使用 <b>word</b><span style="color:#bc8a86; font-size: 0.9em;">【中文】</span> 格式标注...)
                </p>
                
                <div style="background-color: #f3ebe9; padding: 15px 20px; border-radius: 4px; font-family: sans-serif; font-size: 14px; color: #5d4037; border-left: 4px solid #bc8a86; margin-top: 10px;">
                    <div style="font-weight: bold; color: #bc8a86; margin-bottom: 5px;">🦉 Long Sentence Breakdown</div>
                    <div style="line-height: 1.6;">
                        (这里引用那个长难句)<br>
                        <span style="color: #888;">👉 解析：(简要分析语法结构，如定语从句、倒装等)</span>
                    </div>
                </div>

            </div>
            <div style="text-align: center; margin-top: 60px; padding-top: 30px; border-top: 1px solid #dcc1be;">
                <p style="font-size: 20px; font-style: italic; color: #8d6e63; margin-bottom: 15px;">
                    " (请摘录金句) "
                </p>
                <div style="font-size: 12px; color: #bc8a86; text-transform: uppercase; letter-spacing: 1px; font-family: sans-serif;">Goodnight & Sweet Dreams</div>
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
    print("🌙 晚报 Agent 启动...")
    article_data = get_filtered_article() 
    
    if article_data:
        html_content = generate_evening_html(article_data)
        
        if html_content:
            
            # 只有生成成功才保存历史
            if article_data.get('link'):
                save_history(article_data['link'])
            
            # 推送到 Google Sheets
            subject = f"Evening Brief: {today_str}"
            push_to_sheets("evening", subject, html_content)
            print("😏已push到Google Sheet")
            
            return html_content
