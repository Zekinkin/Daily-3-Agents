import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime
import traceback
import datetime
from datetime import timedelta, timezone # 👈 确保加了这行

# 1. 引入发信模块 (新增)
from services.mailer import send_email 

# 2. 定义访问范围
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 3. 密钥路径
CREDS_FILE = os.path.join(os.getcwd(), 'service_account.json')

# 4. 你的表格 ID (保持不变)
SHEET_ID = "1tyu1VH-TSnV20E9uj3T6bmWFluCRZ7Y1bUqPakglXc8" 

def get_client():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"❌ 无法连接 Google Sheets: {e}")
        return None

def push_to_sheets(task_name, subject, html_content):
    """
    上传内容到 'Check' Tab，并同时发送一份预览邮件给自己
    """
    print(f"📤 [Sheets] 正在上传 {task_name} 到表格...")
    
    # --- 1. 上传表格逻辑 ---
    client = get_client()
    upload_success = False
    
    if client:
        try:
            sheet = client.open_by_key(SHEET_ID).worksheet("Check")
            beijing_tz = timezone(timedelta(hours=8))
            now_in_beijing = datetime.datetime.now(beijing_tz)
        
            if now_in_beijing.hour >= 18:
                target_date = now_in_beijing.date() + timedelta(days=1)
            else:
                target_date = now_in_beijing.date()
                
            today_str = target_date.strftime("%Y-%m-%d")
            row_data = [today_str, task_name, subject, html_content, "Pending"]
            
            sheet.insert_row(row_data, 2)
            print(f"✅ 表格上传成功！")
            upload_success = True
        except Exception as e:
            print(f"❌ 表格上传失败: {e}")
            # 即使表格失败了，我们也尝试发邮件，方便排查
    
    # --- 2. 发送预览邮件逻辑 (新增) ---
    print(f"📧 [Preview] 正在发送预览邮件给自己...")
    
    # 给标题加个【预览】前缀，方便区分
    preview_subject = f"【预览 Preview】{subject}"
    
    # 这里不传 to_emails 参数，它会自动读取 .env 里的 MAIL_RECIPIENTS
    # 也就是发给你的测试接收邮箱
    email_success = send_email(preview_subject, html_content)
    
    if email_success:
        print(f"✅ 预览邮件已发送！")
    else:
        print(f"❌ 预览邮件发送失败。")

    return upload_success

# ... (get_active_users 函数保持不变，不用动) ...
def get_active_users():
    # ... (保持原样) ...
    # 为了节省篇幅，这里省略 get_active_users 的代码，请保留你原文件中这部分
    print("👥 正在读取订阅用户列表...")
    client = get_client()
    if not client: return []
    
    try:
        sheet = client.open_by_key(SHEET_ID).worksheet("Users")
        rows = sheet.get_all_values()
        
        if len(rows) < 2:
            print("⚠️ Users 表是空的。")
            return []

        active_emails = []
        today = datetime.date.today()
        
        for i in range(1, len(rows)):
            row = rows[i]
            if len(row) < 4: continue 

            email = row[0]
            expiry_raw = row[3] 
            
            if not email or not expiry_raw: continue
                
            try:
                expiry_str = str(expiry_raw).replace('/', '-').strip()
                expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
                
                if expiry_date >= today:
                    active_emails.append(email)
                else:
                    print(f"  ❌ 用户 {email} 已于 {expiry_date} 过期。")
                    
            except ValueError:
                print(f"  ⚠️ 第 {i+1} 行日期格式错误: '{expiry_raw}'")
                continue
                
        print(f"✅ 有效订阅用户: {len(active_emails)} 人")
        return active_emails

    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return []
