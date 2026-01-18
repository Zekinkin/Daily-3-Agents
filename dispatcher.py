import argparse
import subprocess
import datetime
from services.sheets import get_client, SHEET_ID, get_active_users
from services.mailer import send_email

def check_and_dispatch(mode, target_task=None):
    """
    mode: 'send' (只负责发送 Pending 的特定任务) 或 'monitor' (只负责重写 Reject 的任务)
    target_task: 当 mode='send' 时，指定只发送哪种任务 (morning/afternoon/evening)
    """
    print(f"🔎 [调度员] 启动模式: {mode.upper()}, 目标任务: {target_task if target_task else 'ALL'}")
    
    client = get_client()
    if not client: return
    
    try:
        sheet = client.open_by_key(SHEET_ID).worksheet("Check")
        rows = sheet.get_all_values()
        
        # 获取用户 (仅在发送模式下需要，监控模式不需要发给用户，只需要发预览给自己)
        recipients = []
        if mode == 'send':
            recipients = get_active_users()
            if not recipients:
                print("⚠️ 无有效订阅用户，跳过发送。")
                return

        # 遍历表格 (从最新的一行开始往回看可能更高效，这里保持顺序遍历)
        # 注意：我们只处理"今天"或"明天"的任务？其实只要状态对就行。
        for i in range(1, len(rows)):
            row = rows[i]
            if not row or len(row) < 5: continue
            
            # 数据列: 0:Date, 1:Task, 2:Subject, 3:Content, 4:Status
            row_task = row[1].lower()
            subject = row[2]
            html_content = row[3]
            status = row[4].strip()
            
            # ================= 模式 1: 定点发送 (Send) =================
            if mode == 'send' and target_task:
                # 只有当 任务类型匹配 且 状态是 Approved/Pending 时才发
                if row_task == target_task and status in ["Approved", "Pending"]:
                    print(f"\n🚀 [定时发送] 发现待发任务: 【{subject}】")
                    
                    if send_email(subject, html_content, to_emails=recipients):
                        sheet.update_cell(i+1, 5, "Sent") 
                        print(f"✅ 发送成功，状态已更新为 Sent。")
                    else:
                        print(f"❌ 发送失败。")
            
            # ================= 模式 2: 监控拒绝 (Monitor) =================
            elif mode == 'monitor':
                # 只要状态是 Reject，不管是早中晚报，立刻重写
                if status.lower() == "reject":
                    print(f"\n🛑 [监控] 发现被拒绝任务: 【{subject}】")
                    print(f"🔄 正在触发重生成 (Task: {row_task})...")
                    
                    try:
                        # 标记旧行为 Regenerated
                        sheet.update_cell(i+1, 5, "Regenerated")
                        
                        # 调用 main.py 重写 (生成新的一行 Pending + 预览邮件)
                        # 注意：这里可能生成的是"今天"的日期，如果介意日期问题，后续需优化 main.py
                        subprocess.run(["python", "main.py", "--task", row_task], check=True)
                        print("✅ 重写完成！请检查邮箱预览。")
                        
                    except Exception as e:
                        print(f"❌ 重生成失败: {e}")

    except Exception as e:
        import traceback
        print(f"❌ 调度出错: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=['send', 'monitor'], required=True, help="运行模式: send(发送) 或 monitor(监控拒绝)")
    parser.add_argument("--task", choices=['morning', 'afternoon', 'evening'], help="指定发送的任务类型 (仅在 send 模式下生效)")
    args = parser.parse_args()
    
    check_and_dispatch(args.mode, args.task)
