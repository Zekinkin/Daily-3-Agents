# 环境配置
import os, feedparser, smtplib, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from openai import OpenAI
from dotenv import load_dotenv
import time
from newspaper import Article
from IPython.display import display, HTML
from services.sheets import push_to_sheets
load_dotenv() # 加载你的 .env 文件
print("环境配置已加载")


# RSS信息源
RSS_URLS = [
    # 💵 市场与经济 (Market & Economy)
    "https://www.cnbc.com/id/10000664/device/rss/rss.html", # CNBC Finance
    "https://feeds.bloomberg.com/markets/news.rss",        # Bloomberg Markets
    # 🚀 科技 (Technology)
    "https://techcrunch.com/feed/",                         # TechCrunch
    "https://www.theverge.com/rss/index.xml",               # The Verge
    # 🎬 娱乐 (Entertainment) - 还是保留一点轻松的
    "https://www.eonline.com/news/rss.xml",                 # E! Online
    "https://variety.com/feed/",                            # Variety (偏产业向的娱乐新闻)
    # 🎨 文化 (Culture)
    "https://www.newyorker.com/feed/culture",               # New Yorker Culture
    "https://www.theguardian.com/culture/rss",              # Guardian Culture
]


TIME_WINDOW_HOURS = 24

# get_rss_news
def is_recent(entry_date):
    """
    判断新闻是否在时间窗口内 (过去 24 小时)
    """
    if not entry_date:
        return True # 如果源没给时间，默认收录，以免漏掉
    
    # 获取当前时间 (UTC)
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # 计算时间差
    # 注意：feedparser 解析的时间通常已经是 UTC 或带时区的
    try:
        # 如果 entry_date 还没有时区信息，加上 UTC
        if entry_date.tzinfo is None:
            entry_date = entry_date.replace(tzinfo=datetime.timezone.utc)
            
        time_diff = now - entry_date
        
        # 判断是否在窗口内
        return time_diff.total_seconds() < (TIME_WINDOW_HOURS * 3600)
    except Exception:
        # 如果时间格式解析比对出错，为了保险起见，保留该条目
        return True

def get_rss_news(urls):
    print(f"🔍 正在扫描过去 {TIME_WINDOW_HOURS} 小时的新闻概要...")
    
    all_snippets = []
    
    for url in urls:
        try:
            print(f"  - 正在读取: {url} ...")
            feed = feedparser.parse(url)
            
            count = 0
            for entry in feed.entries:
                # 1. 解析时间
                published_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    # 将 struct_time 转为 datetime
                    published_date = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed), datetime.timezone.utc)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published_date = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed), datetime.timezone.utc)
                
                # 2. 时间过滤
                if not is_recent(published_date):
                    continue # 太旧了，跳过
                
                # 3. 提取摘要 (仅摘要，不要正文)
                title = entry.title
                link = entry.link
                # 有些源把摘要放在 summary，有些在 description
                summary = entry.get('summary', entry.get('description', 'No summary'))
                
                # 清洗一下 HTML 标签 (简单处理，主要靠 LLM 读)
                # 截取前 300 个字符，只要大意
                clean_summary = summary[:300].replace('\n', ' ')
                
                # 格式化成一段小文本
                snippet = f"【标题】{title}\n【来源】{feed.feed.get('title', 'Unknown')}\n【摘要】{clean_summary}\n【链接】{link}\n"
                all_snippets.append(snippet)
                count += 1
                
                # 每个源最多取前 5 条最新的，防止某个源刷屏
                if count >= 5:
                    break
                    
        except Exception as e:
            print(f"❌ 读取失败: {url} - {e}")
            continue

    if not all_snippets:
        return None
        
    print(f"⚡️ 扫描完成！共获取 {len(all_snippets)} 条最新资讯。")
    # 将列表拼成一个长字符串给 AI
    return "\n\n".join(all_snippets)


# get_news_summary
def get_news_summary(raw_text):
    print("🧠 正在生成【早报：四大板块新闻】（深蓝商务版）...")
    
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )

    # --- 1. System Prompt: 国际新闻主编人设 ---
    system_prompt = """
    你是一位视野开阔的《全球晨报》主编。
    你的任务是从杂乱的资讯中筛选出最具价值的新闻，并将其归类整理。
    你的文风简洁、专业，适合商务人士快速阅读。
    同时，你也是一位语言专家，会在每条新闻后顺带提炼一个地道的英语表达（Idiom/Term）。
    切记：先用英文给出概括，在已概括的文本上选取重难点表达/词汇进行讲解，并在英文概括部分把对应的表达用下划线给出（如果涉及短语，就把整个短语用下划线给出）。
    千万“不允许”出现选取的重难点表达/词汇“不存在”英文概括中 的情况。
    """

    # --- 2. User Prompt: 定义深蓝色皮肤与四大板块结构 ---
    user_prompt = f"""
    今天是 {datetime.date.today()}。
    
    【任务目标】：
    请阅读以下原始资讯池，筛选并整理出 **4 个固定板块** 的新闻内容。
    每个板块筛选 **3 条** 最重要的新闻。
    
    【板块顺序】：
    1. 💵 市场与经济 (Market & Economy)
    2. 🚀 科技前沿 (Technology)
    3. 🎬 娱乐动态 (Entertainment)
    4. 🎨 文化观察 (Culture)

    【原始资讯池】：
    {raw_text}

    【输出格式要求 - 必须严格遵守 HTML 格式】：
    请输出一段完整的 HTML 代码。不要使用 Markdown。
    
    请严格按照以下结构生成，**必须将所有内容包裹在指定的深蓝色背景容器中**：

    <div style="background-color: #f0f4f8; padding: 20px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333;">
        
        <div style="max-width: 800px; margin: 0 auto; margin-bottom: 30px; border-bottom: 4px solid #1a365d; padding-bottom: 20px;">
            <h1 style="color: #1a365d; font-size: 36px; margin-bottom: 10px; font-weight: 900; letter-spacing: 1px;">Global Morning Brief</h1>
            <p style="color: #4a5568; font-size: 16px; font-weight: 500;">
                {datetime.date.today().strftime('%A, %B %d, %Y')} | 每日精选，洞见全球
            </p>
        </div>

        <div style="max-width: 800px; margin: 0 auto;">

            <div style="margin-bottom: 40px;">
                <h2 style="background-color: #2c5282; color: white; padding: 10px 15px; border-radius: 6px; font-size: 20px; display: inline-block;">💵 Market & Economy</h2>
                <hr style="border: 0; border-top: 2px solid #2c5282; margin-top: 0; margin-bottom: 20px;">
                
                <div style="background-color: white; border-left: 5px solid #2c5282; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                    <div style="font-size: 16px; font-weight: bold; color: #2d3748; margin-bottom: 8px;">
                        新闻概述（用英文,3-4句话。<b>⚠️ 重要指令：在**撰写完成后**，请务必挑选 3-5 个值得讲解的重难点词汇（挑选的词汇必须是来自撰写完成后的新闻概述），并直接用 &lt;u&gt;单词&lt;/u&gt; 标签包裹它们。</b>例如：The company decided to &lt;u&gt;pivot&lt;/u&gt; its strategy...)
                    </div>
                    <div style="font-size: 14px; color: #4a5568; line-height: 1.6; margin-bottom: 10px;">
                        把英文的新闻概述翻译成中文。
                    </div>


                    <div style="background-color: #ebf8ff; padding: 15px; border-radius: 6px; font-size: 14px; color: #2c5282; border: 1px solid #bee3f8;">
                        <div style="font-weight: bold; margin-bottom: 8px; font-size: 14px;">💡 表达积累：</div>
                        <ul style="margin: 0; padding-left: 20px; list-style-type: disc; line-height: 1.6;">
                            对英文新闻概述中出现并挑选出来的重难点表达/词汇进行讲解，讲解不限个数，按照以下格式：
                            <li><span style="font-family: monospace; font-weight: bold; color: #2b6cb0;">Word/Phrase 1</span>: 中文释义 <span style="color: #718096;">( 简短例句或用法)</span></li>
                            <li><span style="font-family: monospace; font-weight: bold; color: #2b6cb0;">Word/Phrase 2</span>: 中文释义 <span style="color: #718096;">( 简短例句或用法)</span></li>
                            <li><span style="font-family: monospace; font-weight: bold; color: #2b6cb0;">Word/Phrase 3</span>: 中文释义 <span style="color: #718096;">( 简短例句或用法)</span></li>
                            ...（如果有更多讲解同理按照上面格式）
                            </ul>
                    </div>

                </div>
                </div>

            <div style="margin-bottom: 40px;">
                <h2 style="background-color: #2b6cb0; color: white; padding: 10px 15px; border-radius: 6px; font-size: 20px; display: inline-block;">🚀 Technology</h2>
                <hr style="border: 0; border-top: 2px solid #2b6cb0; margin-top: 0; margin-bottom: 20px;">
                </div>

            <div style="margin-bottom: 40px;">
                <h2 style="background-color: #3182ce; color: white; padding: 10px 15px; border-radius: 6px; font-size: 20px; display: inline-block;">🎬 Entertainment</h2>
                <hr style="border: 0; border-top: 2px solid #3182ce; margin-top: 0; margin-bottom: 20px;">
                </div>

            <div style="margin-bottom: 40px;">
                <h2 style="background-color: #4299e1; color: white; padding: 10px 15px; border-radius: 6px; font-size: 20px; display: inline-block;">🎨 Culture</h2>
                <hr style="border: 0; border-top: 2px solid #4299e1; margin-top: 0; margin-bottom: 20px;">
                </div>

            <div style="text-align: center; margin-top: 50px; border-top: 1px solid #cbd5e0; padding-top: 20px; color: #718096; font-size: 12px;">
                © 2026 Daily Briefing
            </div>

        </div> 
    </div>
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # 这种结构化总结用 V3 (chat) 足够了，速度快
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            temperature=0.2,
            max_tokens=8000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ AI 总结失败: {e}")
        return "AI 暂时无法处理。"
    

def run():
    print("🌅 早报 Agent 启动...")
    raw_news = get_rss_news(RSS_URLS)
    
    if raw_news:
        summary_html = get_news_summary(raw_news)

        # 推送到 Google Sheets
        subject = f"Morning Brief: {datetime.date.today()}"
        push_to_sheets("morning", subject, summary_html)
        print("😏已push到Google Sheet")

        return summary_html
    else:
        print("📭 未抓取到内容。")