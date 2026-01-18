import argparse
import sys
import os

# 导入我们的三个 Agent 模块
from Agents import morning, afternoon, evening

def main():
    # 1. 创建参数解析器
    parser = argparse.ArgumentParser(description="AI News Agent Controller")
    
    # 定义一个叫 --task 的参数
    parser.add_argument(
        '--task', 
        type=str, 
        required=True, 
        choices=['morning', 'afternoon', 'evening'],
        help="请选择要执行的任务: morning, afternoon, 或 evening"
    )

    # 2. 获取用户输入的参数
    args = parser.parse_args()

    print(f"🚀 收到指令，正在启动任务: {args.task} ...")

    # 3. 根据参数调用对应的 run() 函数
    try:
        if args.task == 'morning':
            morning.run()
        elif args.task == 'afternoon':
            afternoon.run()
        elif args.task == 'evening':
            evening.run()
            
    except Exception as e:
        print(f"❌ 程序运行出错: {e}")
        # 这里以后可以加个 发送报错邮件给管理员 的功能

if __name__ == "__main__":
    main()