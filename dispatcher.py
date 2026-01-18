import time
from services.sheets import get_client, SHEET_ID, get_active_users
from services.mailer import send_email

def check_and_dispatch():
    print("🔎 [调度员] 正在检查内容库状态...")
    
    client = get_client()
    if not client: return
    
    try:
        # 1. 打开内容库 (Sheet1)
        sheet = client.open_by_key(SHEET_ID).sheet1
        
        # 获取所有内容
        rows = sheet.get_all_values()
        
        # 遍历每一行 (跳过表头，i 从 1 开始)
        for i in range(1, len(rows)):
            row = rows[i]
            
            # 防止空行
            if not row or len(row) < 5: continue
            
            # E列 (索引4) 是 Status
            status = row[4] 
            
            # 🎯 发现了一条 "Approved" (已审核) 的内容
            if status == "Approved":
                subject = row[2]
                html_content = row[3]
                
                print(f"\n🚀 发现待发送任务: 【{subject}】")
                
                # 2. 获取订阅用户名单
                # 这里调用我们在 sheets.py 里写好的新函数
                recipients = get_active_users()
                
                if not recipients:
                    print("⚠️ 没有找到有效的订阅用户，取消发送。")
                    # 也可以选择不更新状态，或者标记为 "No Users"
                    continue
                
                print(f"📧 准备群发给 {len(recipients)} 人...")
                
                # 3. 执行发送
                # 把用户列表传给 send_email
                if send_email(subject, html_content, to_emails=recipients):
                    # 4. 发送成功，更新状态为 "Sent"
                    # Google Sheets 行号是 i+1
                    sheet.update_cell(i+1, 5, "Sent") 
                    print(f"✅ 第 {i+1} 行状态已更新为 Sent。")
                else:
                    print(f"❌ 发送失败，保持 Approved 状态等待重试。")
            
            elif status == "Pending":
                # 仅仅打印日志，不做操作
                # print(f"  ⏳ 第 {i+1} 行等待审核...")
                pass
                
    except Exception as e:
        import traceback
        print(f"❌ 调度出错: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    check_and_dispatch()