import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime
import traceback

# 1. 定义访问范围
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 2. 密钥路径
CREDS_FILE = os.path.join(os.getcwd(), 'service_account.json')

# 3. ⚠️ 这里必须定义 SHEET_ID，否则 dispatcher 会报错
# 请去浏览器地址栏复制：https://docs.google.com/spreadsheets/d/【就是这一长串】/edit
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
    上传内容到 'Check' 这个 Tab (对应之前的 Sheet1)
    """
    print(f"📤 正在上传 {task_name} 到 Google Sheets...")
    client = get_client()
    if not client: return False
    try:
        # ⚠️ 修改：明确指定写入名为 "Check" 的工作表
        sheet = client.open_by_key(SHEET_ID).worksheet("Check")
        
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        # 你的 "Check" 表看起来是空的，我们假设前5列是: Date, Task, Subject, Content, Status
        row_data = [today_str, task_name, subject, html_content, "Pending"]
        
        # 插入到第2行
        sheet.insert_row(row_data, 2)
        print(f"✅ 上传成功！")
        return True
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        return False

def get_active_users():
    """
    读取 'Users' 表的用户列表
    """
    print("👥 正在读取订阅用户列表...")
    client = get_client()
    if not client: return []
    
    try:
        # ⚠️ 确保读取名为 "Users" 的工作表
        sheet = client.open_by_key(SHEET_ID).worksheet("Users")
        
        # 获取所有数据 (包括表头)
        rows = sheet.get_all_values()
        
        if len(rows) < 2:
            print("⚠️ Users 表是空的。")
            return []

        active_emails = []
        today = datetime.date.today()
        
        # 跳过第1行表头，从第2行数据开始
        for i in range(1, len(rows)):
            row = rows[i]
            # 你的表格列结构 (根据截图):
            # A列(索引0): Email
            # D列(索引3): Expiry_Date
            if len(row) < 4: continue # 防止空行报错

            email = row[0]
            expiry_raw = row[3] 
            
            if not email or not expiry_raw: continue
                
            try:
                # 日期清洗：把 2026/2/18 变成 2026-2-18
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

    except gspread.exceptions.WorksheetNotFound:
        print("❌ 错误：找不到对应的工作表。请检查 Tab 名字是否叫 'Check' 和 'Users'。")
        return []
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return []