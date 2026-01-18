import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ================= 配置区域 (163版) =================
SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465  # 网易邮箱推荐使用 SSL 加密端口
SENDER_EMAIL = os.getenv("MAIL_USERNAME")
SENDER_PASSWORD = os.getenv("MAIL_PASSWORD")
# =================================================

def send_email(subject, html_content, to_emails=None):
    """
    发送 HTML 邮件 (适配 163 邮箱)
    """
    if not to_emails:
        # 如果没有传收件人，尝试从环境变量读取默认列表
        env_recipients = os.getenv("MAIL_RECIPIENTS")
        if env_recipients:
            to_emails = [email.strip() for email in env_recipients.split(',')]
        else:
            print("❌ 未配置收件人，且未传入收件人列表。")
            return False

    print(f"📧 [163 Mail] 正在发送邮件: '{subject}' 给 {len(to_emails)} 位用户...")

    try:
        # 1. 连接服务器 (使用 SSL)
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        
        # 2. 登录
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        # 3. 循环发送
        for recipient in to_emails:
            msg = MIMEMultipart()
            # 发件人显示设置
            msg['From'] = formataddr(("AI News Agent", SENDER_EMAIL))
            msg['To'] = recipient
            msg['Subject'] = subject

            # 邮件正文
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 发送指令
            server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
        
        # 4. 退出
        server.quit()
        print("✅ 邮件发送成功！")
        return True

    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False