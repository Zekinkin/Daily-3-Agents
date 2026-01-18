import time
import subprocess
import os
from services.sheets import get_client, SHEET_ID, get_active_users
from services.mailer import send_email

def check_and_dispatch():
    print("🔎 [调度员] 正在检查内容库状态...")
    
    client = get_client()
    if not client: return
    
    try:
        # 1. 打开内容库
        sheet = client.open_by_key(SHEET_ID).worksheet("Check")
        rows = sheet.get_all_values()
        
        # 2. 获取订阅用户名单 (只读一次，避免重复请求)
        recipients = get_active_users()
        if not recipients:
            print("⚠️ 没有找到有效的订阅用户，本次跳过发送。")
            # 注意：如果没用户，就不应该继续执行发送逻辑，防止空转
            # 但我们仍然需要处理 Reject 的重生成逻辑
        
        # 3. 遍历每一行 (跳过表头)
        for i in range(1, len(rows)):
            row = rows[i]
            if not row or len(row) < 5: continue
            
            # 获取关键信息
            task_name = row[1]
            subject = row[2]
            html_content = row[3]
            status = row[4].strip() # 去除可能的手滑空格
            
            # --- 场景 A: 正常发送 (Approved 或 Pending) ---
            # 只要不是 Reject，不是 Sent，不是 Regenerated，就默认发送
            if status in ["Approved", "Pending"] and recipients:
                print(f"\n🚀 发现待发送任务 ({status}): 【{subject}】")
                print(f"📧 正在群发给 {len(recipients)} 位用户...")
                
                if send_email(subject, html_content, to_emails=recipients):
                    # 更新状态为 Sent
                    sheet.update_cell(i+1, 5, "Sent") 
                    print(f"✅ 发送成功，状态已更新为 Sent。")
                else:
                    print(f"❌ 发送失败，保持状态不变。")

            # --- 场景 B: 用户不满意 (Reject) ---
            elif status.lower() == "reject":
                print(f"\n🛑 发现被拒绝的任务: 【{subject}】")
                print(f"🔄 正在触发重生成逻辑 (Task: {task_name})...")
                
                # 1. 调用 main.py 重写
                # 这里的逻辑是：运行 main.py -> 生成新内容 -> 插入新行(Pending) -> 发预览邮件给你
                try:
                    # 使用 subprocess 调用，相当于在命令行输入 python main.py --task xxx
                    subprocess.run(["python", "main.py", "--task", task_name], check=True)
                    print("✅ 重生成完成！新内容已存入表格并发送预览。")
                    
                    # 2. 标记旧行为 "Regenerated" (已处理)，避免下次重复重写
                    sheet.update_cell(i+1, 5, "Regenerated")
                    
                except Exception as e:
                    print(f"❌ 重生成失败: {e}")

            # --- 场景 C: 已处理或无需处理 ---
            else:
                # Sent, Regenerated, 或其他状态，直接跳过
                pass
                
    except Exception as e:
        import traceback
        print(f"❌ 调度出错: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    check_and_dispatch()
