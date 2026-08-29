import re
import json
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog
from typing import List, Dict, Optional, Tuple
import requests
from dashscope import Generation


def read_file(filepath: str) -> str:
    """根据文件后缀读取文本内容，支持 .txt, .md, .docx, .doc"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.txt', '.md'):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    elif ext == '.docx':
        try:
            from docx import Document
        except ImportError:
            raise ImportError("请先安装 python-docx: pip install python-docx")
        doc = Document(filepath)
        return '\n'.join(para.text for para in doc.paragraphs)
    elif ext == '.doc':
        try:
            import textract
        except ImportError:
            raise ImportError(
                "读取 .doc 需要 textract 库，请安装: pip install textract\n"
                "并确保系统已安装 antiword (Linux/Mac) 或等效工具。"
            )
        text = textract.process(filepath)
        return text.decode('utf-8', errors='ignore')
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()


def select_file() -> str:
    """弹出文件选择对话框，返回所选文件路径，若取消则退出程序"""
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="请选择要处理的文档",
        filetypes=[("支持的文件", "*.txt *.md *.docx *.doc"), ("所有文件", "*.*")]
    )
    root.destroy()
    if not file_path:
        print("未选择文件，程序退出。")
        sys.exit(0)
    return file_path


FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")


def get_tenant_access_token() -> Optional[str]:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("tenant_access_token")
        else:
            print(f"获取飞书token失败：{resp.text}")
    except Exception as e:
        print(f"请求飞书token异常：{e}")
    return None


def get_fs_doc_text(access_token: str, document_id: str) -> Optional[str]:
    """获取飞书新版文档的纯文本内容"""
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/raw_content"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("content", "")
        else:
            print(f"获取飞书文档内容失败：{resp.text}")
    except Exception as e:
        print(f"请求飞书文档异常：{e}")
    return None


def extract_doc_id_from_url(url: str) -> Optional[str]:
    """从飞书文档链接中提取文档ID（新版文档用 /docx/）"""
    try:
        return url.split("/docx/")[-1].split("?")[0]
    except:
        return None


DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "your-api-key-here")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen-max")

SUBJECT_KEYWORDS = ["物理", "化学", "生物", "安全常识", "地理", "历史", "社交常识"]


def call_model(prompt: str, max_try: int = 2) -> str:
    """调用百炼模型生成内容，失败时最多重试 max_try 次"""
    for attempt in range(max_try):
        try:
            response = Generation.call(
                model=MODEL_NAME,
                prompt=prompt,
                api_key=DASHSCOPE_API_KEY,
                result_format='message',
            )
            if response.status_code == 200:
                return response.output.choices[0].message.content.strip()
            else:
                print(f"模型调用失败，状态码：{response.status_code}，信息：{response.message}，尝试 {attempt+1}/{max_try}")
                if attempt < max_try - 1:
                    time.sleep(2)
        except Exception as e:
            print(f"模型调用异常：{e}，尝试 {attempt+1}/{max_try}")
            if attempt < max_try - 1:
                time.sleep(2)
    return ""


def generate_cot(questions: List[str], answers: List[str]) -> str:
    """根据问题和答案生成 COT 思维链"""
    qa_text = ""
    for i, (q, a) in enumerate(zip(questions, answers), 1):
        qa_text += f"问题{i}: {q}\n答案{i}: {a}\n"
    prompt = (
        f"我现在在知识点设计了以下问题和答案{qa_text}，"
        f"帮我设计COT思维链，我的COT思维链格式如下：\n"
        f"第一步：针对图模态，让模型重点关注和知识点相关的图中物体\n"
        f"第二步：针对文，让模型思考相关知识，提示模型着重关注什么样的知识点，以及如何思考这些知识点的运用\n"
        f"第三步：针对图+文模态，让模型结合图片，考虑相关知识，如果发生了一些变化会产生什么样的结果"
    )
    return call_model(prompt)


def generate_pre(questions: List[str], answers: List[str]) -> Tuple[str, str]:
    """生成预先问题和预先答案，返回 (pre_question, pre_answer)"""
    qa_text = ""
    for i, (q, a) in enumerate(zip(questions, answers), 1):
        qa_text += f"问题{i}: {q}\n答案{i}: {a}\n"
    prompt = (
        f"我现在在知识点设计了以下问题和答案{qa_text}，"
        f"帮我设计和该知识点相关的但不直接包含我设计的问题答案的预先问题和预先答案，"
        f"输出格式如下：pre_question:xxxx|pre_answer:xxx"
    )
    result = call_model(prompt)
    if not result:
        return "", ""
    pre_q, pre_a = "", ""
    match_q = re.search(r'pre_question\s*[:：]\s*(.*?)(?:\||$)', result)
    match_a = re.search(r'pre_answer\s*[:：]\s*(.*?)(?:\||$)', result)
    if match_q:
        pre_q = match_q.group(1).strip()
    if match_a:
        pre_a = match_a.group(1).strip()
    return pre_q, pre_a


def get_question_type(answer: str) -> str:
    """根据答案内容判断问题类型：判断题/选择题/简答题"""
    ans = answer.strip()
    if ans in ("对", "错"):
        return "判断题"
    if re.fullmatch(r'[A-F]+', ans):
        return "选择题"
    return "简答题"


def extract_cot(unit_text: str) -> str:
    """从知识点单元文本中提取 COT 思维链内容"""
    cot_keywords = r'(?:COT|COT思维链|COT思维链设计)\s*[：:]'
    match = re.search(cot_keywords, unit_text)
    if not match:
        return ""
    start_pos = match.end()
    remaining = unit_text[start_pos:].strip('\n')
    lines = []
    for line in remaining.split('\n'):
        line_stripped = line.strip()
        if not line_stripped:
            break
        if re.match(r'(问题\d+|答案\d+|pre_question|pre_answer|COT|图片)\s*[：:]', line_stripped):
            break
        lines.append(line_stripped)
    return '\n'.join(lines).strip()


def extract_category_from_filename(filepath: str) -> str:
    """从文件路径中提取学科类别，若找不到则返回'未分类'"""
    basename = os.path.basename(filepath)
    filename_no_ext = os.path.splitext(basename)[0]
    for keyword in sorted(SUBJECT_KEYWORDS, key=len, reverse=True):
        if keyword in filename_no_ext:
            return keyword
    return "未分类"


def parse_doc_to_json(doc_text: str, category: str) -> List[Dict]:
    """解析文档文本，返回 JSON 结构列表"""
    units = re.split(r'(?=图片\d+（知识点：)', doc_text)
    knowledge_units = [u.strip() for u in units if u.strip().startswith("图片")]

    results = []
    for unit_text in knowledge_units:
        title_match = re.search(r'图片\d+（知识点：([^）]+)）', unit_text)
        if not title_match:
            continue
        knowledge_name = title_match.group(1).strip()

        media_files = re.findall(r'media/(image\d+\.\w+)', unit_text)
        file_list = []
        for idx, media in enumerate(media_files, start=1):
            ext = media.split('.')[-1]
            new_name = f"{category}-{knowledge_name}{idx}.{ext}"
            file_list.append(new_name)

        cot_text = extract_cot(unit_text)

        pre_q_match = re.search(r'pre_question\s*[:：]\s*(.*?)$', unit_text, re.MULTILINE)
        pre_a_match = re.search(r'pre_answer\s*[:：]\s*(.*?)$', unit_text, re.MULTILINE)
        pre_question = pre_q_match.group(1).strip() if pre_q_match else ""
        pre_answer = pre_a_match.group(1).strip() if pre_a_match else ""

        questions = []
        answers = []

        q_pattern = re.compile(r'问题(\d+)\s*[:：]\s*(.*?)(?=答案\d+\s*[:：]|问题\d+\s*[:：]|$)', re.DOTALL)
        a_pattern = re.compile(r'答案(\d+)\s*[:：]\s*(.*?)(?=问题\d+\s*[:：]|答案\d+\s*[:：]|$)', re.DOTALL)

        q_dict = {}
        for m in q_pattern.finditer(unit_text):
            num = int(m.group(1))
            text = m.group(2).strip()
            q_dict[num] = text

        a_dict = {}
        for m in a_pattern.finditer(unit_text):
            num = int(m.group(1))
            text = m.group(2).strip()
            a_dict[num] = text

        all_nums = sorted(set(list(q_dict.keys()) + list(a_dict.keys())))
        for num in all_nums:
            q = q_dict.get(num, "")
            a = a_dict.get(num, "")
            if q:
                questions.append(q)
                answers.append(a)
            elif a:
                questions.append("")
                answers.append(a)

        question_types = [get_question_type(a) for a in answers]

        if not cot_text and questions:
            print(f"知识点“{knowledge_name}”缺少 COT，正在生成...")
            cot_text = generate_cot(questions, answers)
        if (not pre_question or not pre_answer) and questions:
            print(f"知识点“{knowledge_name}”缺少预先问答，正在生成...")
            gen_q, gen_a = generate_pre(questions, answers)
            if not pre_question:
                pre_question = gen_q
            if not pre_answer:
                pre_answer = gen_a

        unit_data = {
            "files": file_list,
            "category": category,
            "questions": questions,
            "question_type": question_types,
            "answers": answers,
            "core": knowledge_name,
            "pre_question": pre_question,
            "pre_answer": pre_answer,
            "COT": cot_text
        }
        results.append(unit_data)

    return results


if __name__ == "__main__":
    print("请选择文档来源：")
    print("1 - 本地文件（弹窗选择）")
    print("2 - 飞书云文档（输入链接）")
    choice = input("请输入 1 或 2: ").strip()

    doc_text = ""
    category = "未分类"

    if choice == "1":
        input_file = select_file()
        doc_text = read_file(input_file)
        category = extract_category_from_filename(input_file)

    elif choice == "2":
        if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
            print("错误：请先设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
            sys.exit(1)

        fs_url = input("请输入飞书云文档链接: ").strip()
        document_id = extract_doc_id_from_url(fs_url)
        if not document_id:
            print("未能从链接中提取文档ID，请检查链接格式。")
            sys.exit(1)

        token = get_tenant_access_token()
        if not token:
            print("无法获取飞书访问凭证，请检查 App ID 和 Secret 是否正确。")
            sys.exit(1)

        print("正在获取飞书文档内容...")
        doc_text = get_fs_doc_text(token, document_id)
        if not doc_text:
            print("获取文档内容失败，程序退出。")
            sys.exit(1)

        category = "未分类"
        print("飞书文档读取成功。")
    else:
        print("无效选择，程序退出。")
        sys.exit(1)

    print(f"检测到的学科类别：{category}")
    json_data = parse_doc_to_json(doc_text, category)
    print(json.dumps(json_data, ensure_ascii=False, indent=2))