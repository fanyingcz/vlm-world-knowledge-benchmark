import json
import time
import os
import argparse
import glob
from dashscope import Generation

# 配置 API Key（建议通过环境变量设置）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "your-api-key-here")
MODEL_NAME = "qwen-max"  # 可根据需要更换为 qwen-plus / qwen-turbo 等

# 固定的提示词前缀
PROMPT_PREFIX = "请用简明扼要的语言回答以下科普问题，简要说明原因和结论，回答过程当中不要有除了标点符号之外的特殊符号，回答长度不超过100字。\n问题："

def call_model(question: str) -> str:
    """
    调用百炼模型生成回答，每次独立调用，不带上下文。
    """
    full_prompt = PROMPT_PREFIX + question
    try:
        response = Generation.call(
            model=MODEL_NAME,
            prompt=full_prompt,
            api_key=DASHSCOPE_API_KEY,
            result_format='message',  # 返回 message 格式
        )
        if response.status_code == 200:
            answer = response.output.choices[0].message.content
            return answer.strip()
        else:
            print(f"API 请求失败，状态码：{response.status_code}，错误信息：{response.message}")
            return ""
    except Exception as e:
        print(f"调用模型时发生异常：{e}")
        return ""

def process_json_file(file_path: str, max_count: int = None):
    """
    处理单个 JSON 文件，为每个 pre_question 生成 pre_answer。
    :param file_path: JSON 文件路径
    :param max_count: 最多处理的条目数量（仅统计实际需要调用 API 的条目），None 表示不限制
    """
    print(f"\n========== 开始处理文件：{file_path} ==========")
    # 读取 JSON 文件
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total = len(data)
    print(f"共 {total} 个单元。")

    processed = 0  # 记录实际调用 API 的次数
    skipped_has_answer = 0  # 因已有答案而跳过的数量
    skipped_no_question = 0  # 因无问题而跳过的数量

    for idx, item in enumerate(data, start=1):
        pre_question = item.get("pre_question", "")
        if not pre_question:
            print(f"[{idx}/{total}] 跳过：无 pre_question 字段")
            item["pre_answer"] = ""
            skipped_no_question += 1
            continue

        # 检查是否已有非空答案
        existing_answer = item.get("pre_answer", "")
        if existing_answer and existing_answer.strip():
            print(f"[{idx}/{total}] 跳过：已有 pre_answer（{existing_answer[:30]}...）")
            skipped_has_answer += 1
            continue

        # 若指定了最大处理数量，且已达到限制，则停止处理新条目
        if max_count is not None and processed >= max_count:
            print(f"\n已达到指定处理数量 {max_count}，停止处理。")
            break

        print(f"[{idx}/{total}] 正在为问题生成答案：{pre_question[:50]}...")
        answer = call_model(pre_question)
        if answer:
            item["pre_answer"] = answer
            print(f"  已获得答案：{answer[:100]}...")
        else:
            item["pre_answer"] = ""
            print("  未获得有效答案，留空。")

        processed += 1
        # 适当延时，避免请求频率过高
        time.sleep(1)

    # 写回 JSON 文件（覆盖原文件）
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n文件处理完成：{file_path}")
    print(f"统计：总计 {total} 单元，实际调用 API {processed} 次，因已有答案跳过 {skipped_has_answer} 次，因无问题跳过 {skipped_no_question} 次。")
    return processed, skipped_has_answer, skipped_no_question

def get_json_files():
    """获取当前目录下所有 .json 文件列表"""
    files = glob.glob("*.json")
    return sorted(files)

def interactive_select_file():
    """交互式选择要处理的 JSON 文件"""
    files = get_json_files()
    if not files:
        print("当前目录下没有 JSON 文件。")
        return None

    print("当前目录下的 JSON 文件：")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")
    print("  a. 全部文件")
    print("  q. 退出")

    while True:
        choice = input("请输入编号（或 a/q）：").strip().lower()
        if choice == 'q':
            return None
        elif choice == 'a':
            return files  # 返回全部文件列表
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return [files[idx]]
            else:
                print("编号无效，请重新输入。")
        else:
            print("输入无效，请重新输入。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="为 JSON 中的科普问题生成答案（百炼大模型）")
    parser.add_argument("json_file", nargs="?", default=None, help="要处理的 JSON 文件路径（不指定则进入交互选择）")
    parser.add_argument("--count", "-c", type=int, default=None, help="最多生成答案的数量（仅统计实际调用 API 的条目），不指定则处理全部")
    parser.add_argument("--all", "-a", action="store_true", help="处理当前目录下所有 JSON 文件")
    args = parser.parse_args()

    # 确定要处理的文件列表
    files_to_process = []

    if args.all:
        files_to_process = get_json_files()
        if not files_to_process:
            print("当前目录下没有 JSON 文件。")
            exit(0)
        print(f"将处理以下文件：{', '.join(files_to_process)}")
    elif args.json_file:
        # 指定了具体文件名
        if os.path.exists(args.json_file):
            files_to_process = [args.json_file]
        else:
            print(f"文件 {args.json_file} 不存在，请检查路径。")
            exit(1)
    else:
        # 未指定文件，进入交互选择
        files_to_process = interactive_select_file()
        if files_to_process is None:
            print("未选择文件，程序退出。")
            exit(0)

    # 处理每个文件
    total_processed = 0
    for file_path in files_to_process:
        processed, _, _ = process_json_file(file_path, max_count=args.count)
        total_processed += processed

    print(f"\n全部任务完成！共处理 {len(files_to_process)} 个文件，总计调用 API {total_processed} 次。")