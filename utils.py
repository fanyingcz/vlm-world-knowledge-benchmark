import os
import base64
import re
import json
import random
from typing import List, Dict, Tuple, Optional

# 避免循环引用，config 中的东西在函数内导入

def remove_think_tags(text: str) -> str:
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime_type(image_path: str) -> str:
    """根据文件扩展名返回对应的 MIME 类型"""
    ext = os.path.splitext(image_path)[1].lower()
    if ext in ('.png',):
        return 'image/png'
    # jpg、jpeg 统一使用 image/jpeg
    return 'image/jpeg'


def build_image_data_url(image_path: str) -> str:
    """生成完整的 data URL，自动识别图片 MIME 类型"""
    base64_data = encode_image_to_base64(image_path)
    mime = get_image_mime_type(image_path)
    return f"data:{mime};base64,{base64_data}"


def build_messages_with_image(question: str, image_path: str, system_prompt: str) -> List[Dict]:
    image_data_url = build_image_data_url(image_path)
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": question},
            ],
        }
    ]


def evaluate_choice(model_answer: str, correct_answer: str) -> bool:
    model_letters = sorted(set(re.findall(r'[A-Ha-h]', model_answer)))
    correct_letters = sorted(set(re.findall(r'[A-Ha-h]', correct_answer)))
    if not model_letters:
        return False
    return model_letters == correct_letters


def evaluate_true_false(model_answer: str, correct_answer: str) -> bool:
    true_set = {"对", "正确", "true", "t", "是", "yes", "y", "✔", "✓"}
    false_set = {"错", "错误", "false", "f", "否", "no", "n", "✗", "✘"}
    model_low = model_answer.strip().lower()
    correct_low = correct_answer.strip().lower()
    model_bool = model_low in true_set
    correct_bool = correct_low in true_set
    return model_bool == correct_bool


def evaluate_short_answer_with_llm(question: str, model_answer: str, correct_answer: str, core: str = "") -> Tuple[bool, str]:
    import anthropic
    prompt = f"""
你是一位专业的科学老师，正在评估一份学生答卷。
**评分原则：**
不需要学生答案在表述程度上也和标准答案完全一致，只要是和标准答案表达相同或者类似的意思即可
只要学生的回答在核心科学原理上与标准答案一致，即使表述更详细、使用了不同的词汇，也应判定为“正确”。只应在回答有明确科学错误或与标准答案完全相反时，才判定为“错误”。不要因为回答的篇幅长短而影响判断。

**题目：** {question}
**标准答案：** {correct_answer}
{("**评分要点：**" + core) if core else ""}
**学生答案：** {model_answer}

请严格按照以下格式进行评估，不要遗漏任何部分：
**推理：** [在这里写出你的分析，比较学生答案与标准答案的核心原理是否一致]
**判定：** [只输出一个词：正确 或 错误]
"""
    minimax_api_key = os.getenv("MINIMAX_API_KEY")
    if not minimax_api_key:
        raise RuntimeError("环境变量 MINIMAX_API_KEY 未设置，无法评估简答题")

    base_url = "https://api.minimaxi.com"
    try:
        eval_client = anthropic.Anthropic(
            api_key=minimax_api_key,
            base_url=f"{base_url}/anthropic"
        )
        response = eval_client.messages.create(
            model="MiniMax-M2.5",
            max_tokens=5000,
            temperature=0.1,
            system="你是一个严格的评分助手，请严格按照格式输出：先写推理，再写判定。",
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "disabled"}
        )
        eval_output = ""
        for block in response.content:
            if block.type == "text":
                eval_output += block.text
        eval_output = eval_output.strip()
        match = re.search(r'判定[：:]\s*([正错][确误]?)', eval_output, re.IGNORECASE)
        if match:
            verdict = match.group(1)
            is_correct = ("正确" in verdict) or ("正" in verdict and "错" not in verdict)
        else:
            is_correct = ("正确" in eval_output) and ("错误" not in eval_output)
        return is_correct, eval_output
    except Exception as e:
        return False, f"评估简答题出错: {e}"


def fix_json_file(file_path: str) -> Tuple[int, int, int, float]:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fixed_count = 0
    for item in data['detailed_results']:
        if item.get('type') != '简答题':
            continue
        eval_text = item.get('short_answer_evaluation', '')
        match = re.search(r'\*\*判定：\*\*\s*(正确|错误)', eval_text)
        if not match:
            continue
        judgement = match.group(1)
        expected = (judgement == '正确')
        actual = item.get('is_correct')
        if actual != expected:
            item['is_correct'] = expected
            fixed_count += 1

    total_questions = len(data['detailed_results'])
    correct_count = sum(1 for item in data['detailed_results'] if item.get('is_correct') is True)
    accuracy_percent = round(correct_count / total_questions * 100, 2) if total_questions > 0 else 0.0

    data['summary']['total_questions'] = total_questions
    data['summary']['correct_count'] = correct_count
    data['summary']['incorrect_count'] = total_questions - correct_count
    data['summary']['accuracy_percent'] = accuracy_percent

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return fixed_count, total_questions, correct_count, accuracy_percent


def _get_cross_subject_candidates(current_json_path: str) -> List[Dict]:
    from config import JSON_FILE_MAP
    candidates = []
    current_subject_name = os.path.splitext(os.path.basename(current_json_path))[0]
    other_keys = [
        key for key, info in JSON_FILE_MAP.items()
        if os.path.splitext(os.path.basename(info["file"]))[0] != current_subject_name
    ]
    for key in other_keys:
        other_json_path = JSON_FILE_MAP[key]["file"]
        if not os.path.exists(other_json_path):
            continue
        try:
            with open(other_json_path, "r", encoding="utf-8") as f:
                other_data = json.load(f)
            for idx, subj in enumerate(other_data, start=1):
                pq = subj.get("pre_question", "")
                pa = subj.get("pre_answer", "")
                if pq and pq.strip() and pa and pa.strip():
                    candidates.append({
                        "subject_name": os.path.splitext(os.path.basename(other_json_path))[0],
                        "subject_index": idx,
                        "pre_question": pq.strip(),
                        "pre_answer": pa.strip(),
                    })
        except Exception:
            continue
    return candidates


def extract_knowledge_point_name(files: List[str]) -> str:
    if not files:
        return "未命名"
    first = files[0]
    name = os.path.splitext(first)[0]
    if '-' in name:
        parts = name.split('-', 1)
        base = parts[1].strip()
    else:
        base = name
    base = re.sub(r'\d+$', '', base).strip()
    return base if base else "未命名"


def evaluate_single_question(subject_key: str, unit_index: int, image_filename: str,
                             question_text: str, question_type: str, correct_answer: str,
                             core: str, model_key: str, mode: int, custom_prompt: str = "") -> Dict:
    from config import JSON_FILE_MAP, call_vision_model, call_vision_model_with_messages
    json_file = JSON_FILE_MAP[subject_key]["file"]
    image_folder = JSON_FILE_MAP[subject_key]["image_folder"]
    with open(json_file, 'r', encoding='utf-8') as f:
        subjects = json.load(f)
    if unit_index >= len(subjects):
        return {"error": "无效的知识点索引"}

    unit = subjects[unit_index]

    default_system_prompt = """
    对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
    按照以下要求回答以下问题：
    1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
    2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
    3. 对于简答题:可以自由回答，输出完整的中文解释。
    """

    if mode == 3:
        base = custom_prompt if custom_prompt else default_system_prompt
        cot = unit.get('COT', '')
        if cot:
            system_prompt = (base + "\n\n【思考步骤参考】\n" + cot +
                             "\n\n 注意：以上思考步骤仅为解题引导，请**不要**直接回答其中的子问题，你必须要回答的是用户随后提出的实际提问。")
        else:
            system_prompt = base
    else:
        system_prompt = default_system_prompt

    image_path = os.path.join(image_folder, image_filename)
    if not os.path.exists(image_path):
        return {"error": f"图片文件不存在: {image_filename}"}

    context_messages = None
    if mode == 2:
        pre_q = unit.get('pre_question', '')
        pre_a = unit.get('pre_answer', '')
        if pre_q and pre_a:
            context_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pre_q},
                {"role": "assistant", "content": pre_a}
            ]
    elif mode == 4:
        candidates = _get_cross_subject_candidates(json_file)
        if candidates:
            chosen = random.choice(candidates)
            pre_q = chosen["pre_question"]
            pre_a = chosen["pre_answer"]
            context_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pre_q},
                {"role": "assistant", "content": pre_a}
            ]

    if context_messages:
        image_data_url = build_image_data_url(image_path)
        messages = context_messages.copy()
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": question_text},
            ]
        })
        model_ans = call_vision_model_with_messages(messages, model_key)
    else:
        model_ans = call_vision_model(question_text, image_path, system_prompt, model_key)

    is_correct = False
    eval_content = ""
    if question_type == "选择题":
        is_correct = evaluate_choice(model_ans, correct_answer)
    elif question_type == "判断题":
        is_correct = evaluate_true_false(model_ans, correct_answer)
    elif question_type == "简答题":
        is_correct, eval_content = evaluate_short_answer_with_llm(question_text, model_ans, correct_answer, core)
    else:
        is_correct = (model_ans == correct_answer)

    return {
        "model_answer": model_ans,
        "correct_answer": correct_answer,
        "is_correct": is_correct,
        "evaluation": eval_content,
        "type": question_type
    }


# ============ 为 /api/analyze 拆分的分析函数 ============
def analyze_cross_model(file_data):
    """对多模型同一学科进行分析，返回结果字典"""
    from collections import defaultdict

    summaries = [{
        'model': d['model'],
        'test_mode': d['test_mode'],
        'accuracy_percent': d['summary'].get('accuracy_percent', 0),
        'weighted_acc': d['summary'].get('weighted_acc', 0)
    } for d in file_data]

    all_records = []
    for d in file_data:
        for item in d['detailed_results']:
            all_records.append({
                'subject_index': item['subject_index'],
                'question_index_in_subject': item['question_index_in_subject'],
                'image': item.get('image', ''),
                'type': item.get('type', ''),
                'model_used': item.get('model_used', d['model']),
                'test_mode': item.get('test_mode', d['test_mode']),
                'is_correct': item.get('is_correct', False)
            })

    # 模式总体准确率
    mode_stats = {}
    for r in all_records:
        m = r['test_mode']
        if m not in mode_stats:
            mode_stats[m] = {'total': 0, 'correct': 0}
        mode_stats[m]['total'] += 1
        if r['is_correct']:
            mode_stats[m]['correct'] += 1
    mode_overall = [{
        'mode': str(k),
        'total': v['total'],
        'correct': v['correct'],
        'accuracy': round(v['correct'] / v['total'] * 100, 2) if v['total'] else 0
    } for k, v in mode_stats.items()]

    # 模型总体准确率
    model_stats = {}
    for r in all_records:
        m = r['model_used']
        if m not in model_stats:
            model_stats[m] = {'total': 0, 'correct': 0}
        model_stats[m]['total'] += 1
        if r['is_correct']:
            model_stats[m]['correct'] += 1
    model_list = list(model_stats.keys())
    model_overall = [{
        'model': k,
        'total': v['total'],
        'correct': v['correct'],
        'accuracy': round(v['correct'] / v['total'] * 100, 2) if v['total'] else 0
    } for k, v in model_stats.items()]

    # 按问题粒度聚合
    question_groups = defaultdict(list)
    for r in all_records:
        key = (r['subject_index'], r['question_index_in_subject'], r['image'])
        question_groups[key].append(r)

    all_combinations = set()
    for r in all_records:
        all_combinations.add((r['model_used'], r['test_mode']))
    all_columns = [
        f"{model}-mode{mode}"
        for model, mode in sorted(all_combinations, key=lambda x: (x[0], x[1]))
    ]

    questions = []
    for (subj_idx, q_idx, img), records in question_groups.items():
        total = len(records)
        correct = sum(1 for r in records if r['is_correct'])
        accuracy = round(correct / total * 100, 2) if total else 0

        details = {}
        for col in all_columns:
            model, mode_str = col.rsplit('-mode', 1)
            mode = int(mode_str)
            matched = [r for r in records if r['model_used'] == model and r['test_mode'] == mode]
            details[col] = matched[0]['is_correct'] if matched else None

        question_type = records[0]['type']
        question_id = f"{subj_idx}-{q_idx}-{img}"
        questions.append({
            'question_id': question_id,
            'question_type': question_type,
            'accuracy': accuracy,
            'details': details
        })

    questions.sort(key=lambda x: x['accuracy'])

    return {
        'mode': 'cross-model',
        'all_columns': all_columns,
        'models': model_list,
        'summaries': summaries,
        'mode_overall_accuracy': mode_overall,
        'model_overall_accuracy': model_overall,
        'questions': questions
    }


def analyze_cross_subject(file_data):
    """
    对单一模型多学科进行分析，增加模式维度和学科维度的准确率统计。
    file_data: 列表，每个元素包含 subject, test_mode, model, summary, detailed_results
    """
    from collections import defaultdict

    # 题型权重映射（与系统评测保持一致）
    TYPE_WEIGHTS = {"选择题": 2, "判断题": 1, "简答题": 4}

    # 汇总所有记录
    all_records = []
    for d in file_data:
        subject = d['subject']
        test_mode = d['test_mode']
        for item in d['detailed_results']:
            all_records.append({
                'subject': subject,
                'test_mode': test_mode,
                'type': item.get('type', ''),
                'is_correct': item.get('is_correct', False),
            })

    # 1. 总体统计（原有功能）
    total = len(all_records)
    correct = sum(1 for r in all_records if r['is_correct'])
    overall_accuracy = round(correct / total * 100, 2) if total else 0

    # 总体加权准确率
    total_weighted_score = 0
    total_weight = 0
    for r in all_records:
        w = TYPE_WEIGHTS.get(r['type'], 0)
        total_weight += w
        if r['is_correct']:
            total_weighted_score += w
    overall_weighted_acc = round(total_weighted_score / total_weight, 4) if total_weight else 0

    # 2. 按题型统计（原有功能）
    type_stats = {}
    for r in all_records:
        t = r['type']
        if t not in type_stats:
            type_stats[t] = {'total': 0, 'correct': 0}
        type_stats[t]['total'] += 1
        if r['is_correct']:
            type_stats[t]['correct'] += 1
    type_accuracy = [{
        'type': k,
        'total': v['total'],
        'correct': v['correct'],
        'accuracy': round(v['correct'] / v['total'] * 100, 2) if v['total'] else 0
    } for k, v in type_stats.items()]

    # 3. 按测试模式统计
    mode_stats = defaultdict(lambda: {'total': 0, 'correct': 0, 'weighted_score': 0, 'weight': 0})
    for r in all_records:
        m = r['test_mode']
        w = TYPE_WEIGHTS.get(r['type'], 0)
        mode_stats[m]['total'] += 1
        mode_stats[m]['weight'] += w
        if r['is_correct']:
            mode_stats[m]['correct'] += 1
            mode_stats[m]['weighted_score'] += w
    mode_performance = []
    for mode, stat in mode_stats.items():
        acc = round(stat['correct'] / stat['total'] * 100, 2) if stat['total'] else 0
        weighted_acc = round(stat['weighted_score'] / stat['weight'], 4) if stat['weight'] else 0
        mode_performance.append({
            'test_mode': mode,
            'total_questions': stat['total'],
            'correct_count': stat['correct'],
            'accuracy_percent': acc,
            'weighted_acc': weighted_acc
        })
    # 按模式编号排序
    mode_performance.sort(key=lambda x: x['test_mode'])

    # 4. 按学科统计
    subject_stats = defaultdict(lambda: {'total': 0, 'correct': 0, 'weighted_score': 0, 'weight': 0})
    for r in all_records:
        subj = r['subject']
        w = TYPE_WEIGHTS.get(r['type'], 0)
        subject_stats[subj]['total'] += 1
        subject_stats[subj]['weight'] += w
        if r['is_correct']:
            subject_stats[subj]['correct'] += 1
            subject_stats[subj]['weighted_score'] += w
    subject_performance = []
    for subj, stat in subject_stats.items():
        acc = round(stat['correct'] / stat['total'] * 100, 2) if stat['total'] else 0
        weighted_acc = round(stat['weighted_score'] / stat['weight'], 4) if stat['weight'] else 0
        subject_performance.append({
            'subject': subj,
            'total_questions': stat['total'],
            'correct_count': stat['correct'],
            'accuracy_percent': acc,
            'weighted_acc': weighted_acc
        })
    # 按学科名称排序
    subject_performance.sort(key=lambda x: x['subject'])

    return {
        'mode': 'cross-subject',
        'model': file_data[0]['model'],          # 假设所有文件同一模型
        'total': total,
        'overall_accuracy': overall_accuracy,
        'overall_weighted_acc': overall_weighted_acc,
        'type_accuracy': type_accuracy,
        'mode_performance': mode_performance,    # 新增
        'subject_performance': subject_performance  # 新增
    }


def parse_filename(filename):
    name = os.path.splitext(filename)[0]
    parts = name.split('_')
    if len(parts) != 4:
        raise ValueError(f"文件名格式错误，应为 学科_test_modeX_模型.json，实际为: {filename}")
    subject = parts[0]
    test_mode_str = parts[2]
    if not test_mode_str.startswith('mode'):
        raise ValueError(f"测试模式字段格式错误: {test_mode_str}")
    test_mode = int(test_mode_str.replace('mode', ''))
    model = parts[3]
    return subject, test_mode, model


def load_json(file_storage):
    try:
        return json.load(file_storage.stream)
    except Exception as e:
        raise ValueError(f"读取 JSON 文件失败: {str(e)}")


# ==================== 新增：核心评估函数（支持数据库数据源） ====================
def evaluate_single_question_core(subject_key, image_filename, question_text, question_type,
                                  correct_answer, core, model_key, mode, system_prompt=None,
                                  context_messages=None, custom_prompt=''):
    """
    核心评估函数，不依赖 JSON 文件，直接使用传入的数据。
    参数 context_messages: 如果模式需要上下文，传入已有的消息列表（不含当前问题）
    """
    from config import JSON_FILE_MAP, call_vision_model, call_vision_model_with_messages

    image_folder = JSON_FILE_MAP[subject_key]["image_folder"]
    image_path = os.path.join(image_folder, image_filename)
    if not os.path.exists(image_path):
        return {"error": f"图片文件不存在: {image_filename}"}

    default_system_prompt = """
    对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
    按照以下要求回答以下问题：
    1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
    2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
    3. 对于简答题:可以自由回答，输出完整的中文解释。
    """

    if system_prompt is None:
        system_prompt = default_system_prompt

    # 模式3时自定义提示词优先
    if mode == 3:
        base = custom_prompt if custom_prompt else default_system_prompt
        if system_prompt == default_system_prompt:
            system_prompt = base

    # 根据是否有上下文构造消息
    if context_messages is not None:
        msgs = context_messages.copy()
        if msgs and msgs[0]['role'] == 'system':
            msgs[0]['content'] = system_prompt
        else:
            msgs.insert(0, {"role": "system", "content": system_prompt})

        image_data_url = build_image_data_url(image_path)
        msgs.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": question_text},
            ]
        })
        model_ans = call_vision_model_with_messages(msgs, model_key)
    else:
        model_ans = call_vision_model(question_text, image_path, system_prompt, model_key)

    # 新增：模型返回空字符串时视为错误，触发重试
    if not model_ans or not model_ans.strip():
        return {"error": "模型未返回有效回答"}

    is_correct = False
    eval_content = ""
    if question_type == "选择题":
        is_correct = evaluate_choice(model_ans, correct_answer)
    elif question_type == "判断题":
        is_correct = evaluate_true_false(model_ans, correct_answer)
    elif question_type == "简答题":
        is_correct, eval_content = evaluate_short_answer_with_llm(question_text, model_ans, correct_answer, core)
    else:
        is_correct = (model_ans == correct_answer)

    return {
        "model_answer": model_ans,
        "correct_answer": correct_answer,
        "is_correct": is_correct,
        "evaluation": eval_content,
        "type": question_type
    }

def evaluate_single_question_db(subject_key, unit_index, image_filename, question_text,
                                question_type, correct_answer, core, model_key, mode,
                                custom_prompt=''):
    """数据库数据源的单一问题评估，自动从数据库加载场景并构建上下文"""
    import db as database
    from config import JSON_FILE_MAP

    subject_name = os.path.basename(JSON_FILE_MAP[subject_key]['file']).replace('.json', '')
    scenarios = database.get_scenarios_by_category(subject_name)
    if unit_index >= len(scenarios):
        return {"error": "无效的知识点索引"}
    sc = scenarios[unit_index]

    default_system_prompt = """
    对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
    按照以下要求回答以下问题：
    1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
    2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
    3. 对于简答题:可以自由回答，输出完整的中文解释。
    """

    # 构建 system_prompt（考虑 mode 3 的 COT）
    if mode == 3:
        base = custom_prompt if custom_prompt else default_system_prompt
        cot = sc.get('cot', '')
        if cot:
            system_prompt = base + "\n\n【思考步骤参考】\n" + cot + \
                             "\n\n 注意：以上思考步骤仅为解题引导，请**不要**直接回答其中的子问题，你必须要回答的是用户随后提出的实际提问。"
        else:
            system_prompt = base
    else:
        system_prompt = default_system_prompt

    # 构建上下文消息（模式2/4）
    context_messages = None
    if mode == 2:
        pre_q = sc.get('pre_question', '')
        pre_a = sc.get('pre_answer', '')
        if pre_q and pre_a:
            context_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pre_q},
                {"role": "assistant", "content": pre_a}
            ]
    elif mode == 4:
        candidates = _get_cross_subject_candidates_from_db(subject_key)
        if candidates:
            chosen = random.choice(candidates)
            context_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": chosen["pre_question"]},
                {"role": "assistant", "content": chosen["pre_answer"]}
            ]

    return evaluate_single_question_core(
        subject_key=subject_key,
        image_filename=image_filename,
        question_text=question_text,
        question_type=question_type,
        correct_answer=correct_answer,
        core=core,
        model_key=model_key,
        mode=mode,
        system_prompt=system_prompt,
        context_messages=context_messages,
        custom_prompt=custom_prompt
    )


def _get_cross_subject_candidates_from_db(current_subject_key):
    """从数据库获取其他学科的 pre_question 候选（供模式4使用）"""
    import db
    from config import JSON_FILE_MAP
    current_subject_name = os.path.basename(JSON_FILE_MAP[current_subject_key]['file']).replace('.json', '')
    all_categories = [os.path.basename(info['file']).replace('.json', '') for info in JSON_FILE_MAP.values()]
    other_categories = [cat for cat in all_categories if cat != current_subject_name]
    candidates = []
    for cat in other_categories:
        scenarios = db.get_scenarios_by_category(cat)
        for sc in scenarios:
            pq = sc.get('pre_question', '')
            pa = sc.get('pre_answer', '')
            if pq and pa:
                candidates.append({
                    "subject_name": cat,
                    "pre_question": pq.strip(),
                    "pre_answer": pa.strip()
                })
    return candidates