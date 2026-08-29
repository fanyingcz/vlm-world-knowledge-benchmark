import time
import json
import os
import random
import threading
import uuid
import datetime
from typing import Optional, List, Dict

from config import (
    MODEL_CONFIGS,
    JSON_FILE_MAP,
    REQUEST_INTERVAL,
    call_vision_model,
    call_vision_model_with_messages,
)
from utils import (
    encode_image_to_base64,
    build_image_data_url,
    evaluate_choice,
    evaluate_true_false,
    evaluate_short_answer_with_llm,
    _get_cross_subject_candidates,
    extract_knowledge_point_name,
    evaluate_single_question_core,
    _get_cross_subject_candidates_from_db,
)
import db

# ==================== 全局任务状态（线程安全） ====================
task_status = {}
task_logs = {}
task_results = {}
task_pre_contexts = {}
task_result_file = {}
task_info = {}
task_control: Dict[str, dict] = {}   # 任务控制对象
_task_lock = threading.RLock()

def update_task_status(task_id: str, status: str):
    """线程安全地更新任务状态"""
    with _task_lock:
        task_status[task_id] = status

# ==================== 日志文件相关 ====================
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

SUBJECT_EN_MAP = {
    '物理': 'physics',
    '生物': 'biology',
    '化学': 'chemical',
    '安全常识': 'safety'
}

MODEL_EN_MAP = {
    '1': 'Qwen',
    '2': 'Gemini',
    '3': 'Doubao'
}

# ==================== 原有 JSON 数据源的完整评测任务 ====================
def run_evaluation_with_logs(task_id: str, json_path: str, image_folder: str, test_mode: int,
                             model_key: str, max_questions: Optional[int] = None,
                             custom_system_prompt: Optional[str] = None,
                             user_id=None, username=None, subject_key=None):
    task_info[task_id] = {
        'start_time': time.time(),
        'subject_key': subject_key,
        'model_key': model_key,
        'test_mode': test_mode,
        'user_id': user_id,
        'username': username
    }
    update_task_status(task_id, "running")
    task_logs[task_id] = []

    control = {
        'pause_event': threading.Event(),
        'pause_requested': False,
        'stop_requested': False,
        'lock': threading.Lock()
    }
    control['pause_event'].set()
    task_control[task_id] = control

    subject_cn = os.path.splitext(os.path.basename(json_path))[0]
    subject_en = SUBJECT_EN_MAP.get(subject_cn, subject_cn)
    model_en = MODEL_EN_MAP.get(model_key, model_key)
    mode_str = f"mode{test_mode}"
    now = datetime.datetime.now()
    time_str = now.strftime("%Y-%m-%d-%H%M")
    log_filename = f"{time_str}_{subject_en}_{model_en}_{mode_str}.log"
    log_filepath = os.path.join(LOGS_DIR, log_filename)
    os.makedirs(LOGS_DIR, exist_ok=True)

    def log(msg):
        print(msg)
        timestamp = time.time()
        task_logs[task_id].append({"time": timestamp, "msg": msg})
        try:
            formatted_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            line = f"{formatted_time} - {msg}\n"
            with open(log_filepath, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as e:
            print(f"[LOGGING ERROR] 无法写入日志文件 {log_filepath}: {e}")

    try:
        log(f"任务 {task_id} 开始")
        log(f"选择的模型: {MODEL_CONFIGS[model_key]['name']}")
        log(f"测试模式: {test_mode}")
        log(f"学科文件: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        default_system_prompt = """
        对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
        按照以下要求回答以下问题：
        1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
        2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
        3. 对于简答题:可以自由回答，输出完整的中文解释。
        """

        all_results = []
        pre_question_contexts = []
        question_count = 0
        cross_subject_candidates = _get_cross_subject_candidates(json_path)

        for subj_idx, subject in enumerate(data, 1):
            if control['stop_requested']:
                task_results[task_id] = all_results
                task_pre_contexts[task_id] = pre_question_contexts
                update_task_status(task_id, 'stopped')
                return

            while not control['pause_event'].is_set():
                time.sleep(0.5)
                if control['stop_requested']:
                    task_results[task_id] = all_results
                    task_pre_contexts[task_id] = pre_question_contexts
                    update_task_status(task_id, 'stopped')
                    return

            if test_mode == 3:
                base_prompt = custom_system_prompt if custom_system_prompt else default_system_prompt
                cot_content = subject.get("COT")
                if cot_content:
                    current_system_prompt = (
                        base_prompt
                        + "\n\n【思考步骤参考】\n"
                        + cot_content
                        + "\n\n 注意：以上思考步骤仅为解题引导，请**不要**直接回答其中的子问题，你必须要回答的是用户随后提出的实际提问。")
                else:
                    current_system_prompt = base_prompt
            else:
                current_system_prompt = default_system_prompt

            files = subject.get("files", [])
            questions = subject.get("questions", [])
            q_types = subject.get("question_type", [])
            answers = subject.get("answers", [])
            cores = subject.get("core", [])
            original_pre_question = subject.get("pre_question", "")
            original_pre_answer = subject.get("pre_answer", "")

            if not files or not questions:
                log(f"子题目集 {subj_idx} 缺少图片或问题，跳过")
                continue

            log(f"========== 子题目集 {subj_idx}/{len(data)} ==========")
            log(f"图片数: {len(files)}, 问题数: {len(questions)}")

            context_messages = None
            pre_answer = ""
            used_pre_question = ""
            used_pre_subject = None
            used_subject_name = None

            if test_mode == 2:
                if original_pre_question and original_pre_answer:
                    used_pre_question = original_pre_question
                    pre_answer = original_pre_answer
                    used_pre_subject = subj_idx
                    log(f"模式2：使用自身的 pre_question: {used_pre_question}")
                    context_messages = [
                        {"role": "system", "content": current_system_prompt},
                        {"role": "user", "content": used_pre_question},
                        {"role": "assistant", "content": pre_answer}
                    ]
                else:
                    log(f"⚠️ 科目 {subj_idx} 缺少 pre_question 或 pre_answer，模式2退化为无上下文模式")

            elif test_mode == 4:
                if cross_subject_candidates:
                    chosen = random.choice(cross_subject_candidates)
                    used_subject_name = chosen["subject_name"]
                    used_pre_subject = chosen["subject_index"]
                    used_pre_question = chosen["pre_question"]
                    pre_answer = chosen["pre_answer"]
                    log(f"模式4：从其他学科 {used_subject_name} (子题目集 {used_pre_subject}) 随机抽取 pre_question: {used_pre_question}")
                    context_messages = [
                        {"role": "system", "content": current_system_prompt},
                        {"role": "user", "content": used_pre_question},
                        {"role": "assistant", "content": pre_answer}
                    ]
                else:
                    log("模式4无可用跨学科数据，退化为无上下文模式")

            pre_question_contexts.append({
                "subject_index": subj_idx,
                "original_pre_question": original_pre_question,
                "original_pre_answer": original_pre_answer,
                "used_pre_question": used_pre_question if (test_mode in (2,4) and used_pre_question) else "",
                "used_pre_answer": pre_answer if context_messages is not None else "",
                "used_pre_subject_index": used_pre_subject,
                "used_subject_name": used_subject_name if test_mode == 4 else None,
                "mode_used": test_mode
            })

            for img_idx, img_name in enumerate(files):
                image_path = os.path.join(image_folder, img_name)
                if not os.path.exists(image_path):
                    log(f"⚠️ 图片不存在: {image_path}，跳过该图片")
                    continue

                log(f"--- 图片 {img_idx+1}/{len(files)}: {img_name} ---")

                for q_idx, (question, q_type, correct_ans, core) in enumerate(
                        zip(questions, q_types, answers, cores), 1):

                    if max_questions is not None and question_count >= max_questions:
                        log(f"已达到设定提问次数上限 {max_questions}，停止测试。")
                        task_results[task_id] = all_results
                        task_pre_contexts[task_id] = pre_question_contexts
                        update_task_status(task_id, "completed")
                        return

                    log(f"  问题 {q_idx}/{len(questions)} (题型:{q_type})")
                    question_count += 1

                    # ---------- 重试循环：支持暂停/继续，3次失败后自动暂停 ----------
                    attempt = 0
                    model_ans = None
                    while model_ans is None or not model_ans.strip():
                        if control['stop_requested']:
                            task_results[task_id] = all_results
                            task_pre_contexts[task_id] = pre_question_contexts
                            update_task_status(task_id, 'stopped')
                            return

                        while not control['pause_event'].is_set():
                            time.sleep(0.5)
                            if control['stop_requested']:
                                task_results[task_id] = all_results
                                task_pre_contexts[task_id] = pre_question_contexts
                                update_task_status(task_id, 'stopped')
                                return

                        if attempt >= 3:
                            log("任务继续，重新尝试当前问题")
                            attempt = 0

                        attempt += 1
                        try:
                            if context_messages is not None:
                                msgs = context_messages.copy()
                                msgs.append({
                                    "role": "user",
                                    "content": [
                                        {"type": "image_url", "image_url": {"url": build_image_data_url(image_path)}},
                                        {"type": "text", "text": question},
                                    ]
                                })
                                ans = call_vision_model_with_messages(msgs, model_key)
                            else:
                                ans = call_vision_model(question, image_path, current_system_prompt, model_key)

                            if ans and ans.strip():
                                model_ans = ans
                                break
                        except Exception as e:
                            log(f"调用模型出错 (重试 {attempt}/3): {str(e)}")

                        if attempt >= 3:
                            log("3次重试均未得到有效回答，任务自动暂停")
                            update_task_status(task_id, 'paused')
                            control['pause_event'].clear()
                            # 短暂延迟，等待可能的外部恢复
                            time.sleep(0.1)
                            with _task_lock:
                                if task_status.get(task_id) == 'running':
                                    # 如果在延迟期间被恢复了，直接继续重试循环
                                    log("检测到外部恢复指令，取消暂停")
                                    continue
                            continue
                        else:
                            time.sleep(REQUEST_INTERVAL * 2)

                    log(f"  模型回答: {model_ans}")
                    log(f"  标准答案: {correct_ans}")

                    eval_content = ""
                    if q_type == "选择题":
                        is_correct = evaluate_choice(model_ans, correct_ans)
                    elif q_type == "判断题":
                        is_correct = evaluate_true_false(model_ans, correct_ans)
                    elif q_type == "简答题":
                        is_correct, eval_content = evaluate_short_answer_with_llm(question, model_ans, correct_ans, core)
                    else:
                        is_correct = (model_ans == correct_ans)

                    log(f"  判定: {'✓ 正确' if is_correct else '✗ 错误'}")

                    result = {
                        "subject_index": subj_idx,
                        "image": img_name,
                        "question_index_in_subject": q_idx,
                        "question": question,
                        "type": q_type,
                        "model_answer": model_ans,
                        "correct_answer": correct_ans,
                        "is_correct": is_correct,
                        "core": core,
                        "model_used": MODEL_CONFIGS[model_key]["name"],
                        "test_mode": test_mode,
                    }
                    if test_mode in (2,4) and context_messages:
                        result["used_pre_question"] = used_pre_question
                        if test_mode == 4:
                            result["used_pre_subject_index"] = used_pre_subject
                            result["used_subject_name"] = used_subject_name
                    if q_type == "简答题":
                        result["short_answer_evaluation"] = eval_content

                    all_results.append(result)

                    if control['stop_requested']:
                        log("收到停止请求，任务结束")
                        task_results[task_id] = all_results
                        task_pre_contexts[task_id] = pre_question_contexts
                        update_task_status(task_id, 'stopped')
                        return

                    if control['pause_requested']:
                        log("收到暂停请求，任务暂停")
                        update_task_status(task_id, 'paused')
                        control['pause_event'].clear()
                        control['pause_requested'] = False
                        while not control['pause_event'].is_set():
                            time.sleep(0.5)
                            if control['stop_requested']:
                                task_results[task_id] = all_results
                                task_pre_contexts[task_id] = pre_question_contexts
                                update_task_status(task_id, 'stopped')
                                return

                    time.sleep(REQUEST_INTERVAL)

        task_results[task_id] = all_results
        task_pre_contexts[task_id] = pre_question_contexts
        update_task_status(task_id, "completed")
        log("评测完成，请在前端输入文件名以保存结果。")
    finally:
        # 若线程异常退出，且状态为 running 或 paused，则标记为 error
        if task_id in task_status and task_status[task_id] in ('running', 'paused'):
            update_task_status(task_id, 'error')
        task_control.pop(task_id, None)

# ==================== 数据库数据源的完整评测任务 ====================
def run_evaluation_with_logs_db(task_id: str, subject_key: str, test_mode: int,
                                model_key: str, max_questions: Optional[int] = None,
                                custom_system_prompt: Optional[str] = None,
                                user_id=None, username=None):
    subject_name = os.path.basename(JSON_FILE_MAP[subject_key]['file']).replace('.json', '')
    image_folder = JSON_FILE_MAP[subject_key]['image_folder']

    task_info[task_id] = {
        'start_time': time.time(),
        'subject_key': subject_key,
        'model_key': model_key,
        'test_mode': test_mode,
        'user_id': user_id,
        'username': username
    }
    update_task_status(task_id, "running")
    task_logs[task_id] = []

    control = {
        'pause_event': threading.Event(),
        'pause_requested': False,
        'stop_requested': False,
        'lock': threading.Lock()
    }
    control['pause_event'].set()
    task_control[task_id] = control

    subject_en = SUBJECT_EN_MAP.get(subject_name, subject_name)
    model_en = MODEL_EN_MAP.get(model_key, model_key)
    mode_str = f"mode{test_mode}"
    now = datetime.datetime.now()
    time_str = now.strftime("%Y-%m-%d-%H%M")
    log_filename = f"{time_str}_{subject_en}_{model_en}_{mode_str}.log"
    log_filepath = os.path.join(LOGS_DIR, log_filename)
    os.makedirs(LOGS_DIR, exist_ok=True)

    def log(msg):
        print(msg)
        timestamp = time.time()
        task_logs[task_id].append({"time": timestamp, "msg": msg})
        try:
            formatted_time = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            line = f"{formatted_time} - {msg}\n"
            with open(log_filepath, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as e:
            print(f"[LOGGING ERROR] 无法写入日志文件 {log_filepath}: {e}")

    try:
        log(f"任务 {task_id} 开始 [数据源: 数据库]")
        log(f"选择的模型: {MODEL_CONFIGS[model_key]['name']}")
        log(f"测试模式: {test_mode}")
        log(f"学科: {subject_name}")

        default_system_prompt = """
        对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
        按照以下要求回答以下问题：
        1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
        2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
        3. 对于简答题:可以自由回答，输出完整的中文解释。
        """

        all_results = []
        pre_question_contexts = []
        question_count = 0

        scenarios = db.get_scenarios_by_category(subject_name)
        cross_subject_candidates = _get_cross_subject_candidates_from_db(subject_key)

        for subj_idx, sc in enumerate(scenarios, 1):
            if control['stop_requested']:
                task_results[task_id] = all_results
                task_pre_contexts[task_id] = pre_question_contexts
                update_task_status(task_id, 'stopped')
                return

            while not control['pause_event'].is_set():
                time.sleep(0.5)
                if control['stop_requested']:
                    task_results[task_id] = all_results
                    task_pre_contexts[task_id] = pre_question_contexts
                    update_task_status(task_id, 'stopped')
                    return

            scenario_id = sc['id']
            files = db.get_scenario_files(scenario_id)
            questions_data = db.get_scenario_questions(scenario_id)

            if not files or not questions_data:
                log(f"场景 {subj_idx} 缺少图片或问题，跳过")
                continue

            log(f"========== 场景 {subj_idx}/{len(scenarios)} ==========")
            log(f"图片数: {len(files)}, 问题数: {len(questions_data)}")

            if test_mode == 3:
                base_prompt = custom_system_prompt if custom_system_prompt else default_system_prompt
                cot = sc.get('cot', '')
                if cot:
                    current_system_prompt = (base_prompt + "\n\n【思考步骤参考】\n" + cot +
                                             "\n\n 注意：以上思考步骤仅为解题引导，请**不要**直接回答其中的子问题，你必须要回答的是用户随后提出的实际提问。")
                else:
                    current_system_prompt = base_prompt
            else:
                current_system_prompt = default_system_prompt

            context_messages = None
            pre_answer = ""
            used_pre_question = ""
            used_pre_subject = None
            used_subject_name = None

            original_pre_question = sc.get('pre_question', '')
            original_pre_answer = sc.get('pre_answer', '')

            if test_mode == 2:
                if original_pre_question and original_pre_answer:
                    used_pre_question = original_pre_question
                    pre_answer = original_pre_answer
                    used_pre_subject = subj_idx
                    log(f"模式2：使用自身的 pre_question: {used_pre_question}")
                    context_messages = [
                        {"role": "system", "content": current_system_prompt},
                        {"role": "user", "content": used_pre_question},
                        {"role": "assistant", "content": pre_answer}
                    ]
                else:
                    log(f"⚠️ 场景 {subj_idx} 缺少 pre_question 或 pre_answer，模式2退化为无上下文模式")

            elif test_mode == 4:
                if cross_subject_candidates:
                    chosen = random.choice(cross_subject_candidates)
                    used_subject_name = chosen["subject_name"]
                    used_pre_question = chosen["pre_question"]
                    pre_answer = chosen["pre_answer"]
                    log(f"模式4：从其他学科 {used_subject_name} 随机抽取 pre_question: {used_pre_question}")
                    context_messages = [
                        {"role": "system", "content": current_system_prompt},
                        {"role": "user", "content": used_pre_question},
                        {"role": "assistant", "content": pre_answer}
                    ]
                else:
                    log("模式4无可用跨学科数据，退化为无上下文模式")

            pre_question_contexts.append({
                "subject_index": subj_idx,
                "original_pre_question": original_pre_question,
                "original_pre_answer": original_pre_answer,
                "used_pre_question": used_pre_question if (test_mode in (2,4) and used_pre_question) else "",
                "used_pre_answer": pre_answer if context_messages is not None else "",
                "used_pre_subject_index": used_pre_subject,
                "used_subject_name": used_subject_name if test_mode == 4 else None,
                "mode_used": test_mode
            })

            for img_idx, img_name in enumerate(files):
                image_path = os.path.join(image_folder, img_name)
                if not os.path.exists(image_path):
                    log(f"⚠️ 图片不存在: {image_path}，跳过该图片")
                    continue

                log(f"--- 图片 {img_idx+1}/{len(files)}: {img_name} ---")

                for q_idx, q_data in enumerate(questions_data, 1):
                    if max_questions is not None and question_count >= max_questions:
                        log(f"已达到设定提问次数上限 {max_questions}，停止测试。")
                        task_results[task_id] = all_results
                        task_pre_contexts[task_id] = pre_question_contexts
                        update_task_status(task_id, "completed")
                        return

                    question = q_data['question']
                    q_type = q_data['question_type']
                    correct_ans = q_data['answer']
                    core = q_data.get('core', '') or ''
                    log(f"  问题 {q_idx}/{len(questions_data)} (题型:{q_type})")
                    question_count += 1

                    # ---------- 重试循环 ----------
                    attempt = 0
                    res = None
                    while res is None or "error" in res:
                        if control['stop_requested']:
                            task_results[task_id] = all_results
                            task_pre_contexts[task_id] = pre_question_contexts
                            update_task_status(task_id, 'stopped')
                            return

                        while not control['pause_event'].is_set():
                            time.sleep(0.5)
                            if control['stop_requested']:
                                task_results[task_id] = all_results
                                task_pre_contexts[task_id] = pre_question_contexts
                                update_task_status(task_id, 'stopped')
                                return

                        if attempt >= 3:
                            log("任务继续，重新尝试当前问题")
                            attempt = 0

                        attempt += 1
                        try:
                            res = evaluate_single_question_core(
                                subject_key=subject_key,
                                image_filename=img_name,
                                question_text=question,
                                question_type=q_type,
                                correct_answer=correct_ans,
                                core=core,
                                model_key=model_key,
                                mode=test_mode,
                                system_prompt=current_system_prompt,
                                context_messages=context_messages,
                                custom_prompt=custom_system_prompt
                            )
                            if "error" not in res:
                                break
                        except Exception as e:
                            log(f"调用模型出错 (重试 {attempt}/3): {str(e)}")
                            res = {"error": str(e)}

                        if attempt >= 3:
                            log("3次重试均未得到有效回答，任务自动暂停")
                            update_task_status(task_id, 'paused')
                            control['pause_event'].clear()
                            continue
                        else:
                            time.sleep(REQUEST_INTERVAL * 2)

                    if res is None or "error" in res:
                        continue

                    model_ans = res['model_answer']
                    is_correct = res['is_correct']
                    eval_content = res.get('evaluation', '')
                    log(f"  模型回答: {model_ans}")
                    log(f"  标准答案: {correct_ans}")
                    log(f"  判定: {'✓ 正确' if is_correct else '✗ 错误'}")

                    result = {
                        "subject_index": subj_idx,
                        "image": img_name,
                        "question_index_in_subject": q_idx,
                        "question": question,
                        "type": q_type,
                        "model_answer": model_ans,
                        "correct_answer": correct_ans,
                        "is_correct": is_correct,
                        "core": core,
                        "model_used": MODEL_CONFIGS[model_key]["name"],
                        "test_mode": test_mode,
                    }
                    if test_mode in (2,4) and context_messages:
                        result["used_pre_question"] = used_pre_question
                        if test_mode == 4:
                            result["used_pre_subject_index"] = used_pre_subject
                            result["used_subject_name"] = used_subject_name
                    if q_type == "简答题":
                        result["short_answer_evaluation"] = eval_content

                    all_results.append(result)

                    if control['stop_requested']:
                        log("收到停止请求，任务结束")
                        task_results[task_id] = all_results
                        task_pre_contexts[task_id] = pre_question_contexts
                        update_task_status(task_id, 'stopped')
                        return

                    if control['pause_requested']:
                        log("收到暂停请求，任务暂停")
                        update_task_status(task_id, 'paused')
                        control['pause_event'].clear()
                        control['pause_requested'] = False
                        while not control['pause_event'].is_set():
                            time.sleep(0.5)
                            if control['stop_requested']:
                                task_results[task_id] = all_results
                                task_pre_contexts[task_id] = pre_question_contexts
                                update_task_status(task_id, 'stopped')
                                return

                    time.sleep(REQUEST_INTERVAL)

        task_results[task_id] = all_results
        task_pre_contexts[task_id] = pre_question_contexts
        update_task_status(task_id, "completed")
        log("评测完成，请在前端输入文件名以保存结果。")
    finally:
        # 线程异常退出时标记为 error
        if task_id in task_status and task_status[task_id] in ('running', 'paused'):
            update_task_status(task_id, 'error')
        task_control.pop(task_id, None)

# ==================== 原有 JSON 的局部测试函数（暂不实现暂停控制，可按需添加） ====================
def run_question_test(task_id: str, subject_key: str, unit_index: int, question_index: int,
                      model_key: str, mode: int, custom_prompt: str = ""):
    update_task_status(task_id, "running")
    task_logs[task_id] = []
    def log(msg):
        print(msg)
        task_logs[task_id].append({"time": time.time(), "msg": msg})

    from utils import evaluate_single_question

    json_file = JSON_FILE_MAP[subject_key]["file"]
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if unit_index >= len(data):
        update_task_status(task_id, "completed")
        return

    unit = data[unit_index]
    files = unit.get('files', [])
    questions = unit.get('questions', [])
    question_types = unit.get('question_type', [])
    answers = unit.get('answers', [])
    cores = unit.get('core', [])

    if question_index >= len(questions):
        log("问题索引无效")
        update_task_status(task_id, "completed")
        return

    question_text = questions[question_index]
    q_type = question_types[question_index]
    correct_answer = answers[question_index]
    core = cores[question_index] if question_index < len(cores) else ""

    results = []
    for img_name in files:
        log(f"测试图片 {img_name} 问题: {question_text}")
        res = evaluate_single_question(subject_key, unit_index, img_name, question_text,
                                       q_type, correct_answer, core, model_key, mode, custom_prompt)
        if "error" in res:
            log(f"错误: {res['error']}")
        else:
            log(f"模型回答: {res['model_answer']} - {'✓' if res['is_correct'] else '✗'}")
            res['image'] = img_name
            res['question'] = question_text
            res['type'] = q_type
            res['model_used'] = MODEL_CONFIGS[model_key]["name"]
            res['test_mode'] = mode
            results.append(res)
        time.sleep(REQUEST_INTERVAL)

    task_results[task_id] = results
    update_task_status(task_id, "completed")
    log("问题测试完成")


def run_knowledge_test(task_id: str, subject_key: str, unit_index: int,
                       model_key: str, mode: int, custom_prompt: str = ""):
    update_task_status(task_id, "running")
    task_logs[task_id] = []
    def log(msg):
        print(msg)
        task_logs[task_id].append({"time": time.time(), "msg": msg})

    from utils import evaluate_single_question

    json_file = JSON_FILE_MAP[subject_key]["file"]
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if unit_index >= len(data):
        update_task_status(task_id, "completed")
        return

    unit = data[unit_index]
    files = unit.get('files', [])
    questions = unit.get('questions', [])
    question_types = unit.get('question_type', [])
    answers = unit.get('answers', [])
    cores = unit.get('core', [])

    results = []
    for img_name in files:
        for q_idx, (question_text, q_type, correct_answer, core) in enumerate(
                zip(questions, question_types, answers, cores)):
            log(f"图片 {img_name} 题目 {q_idx+1}: {question_text}")
            res = evaluate_single_question(subject_key, unit_index, img_name, question_text,
                                           q_type, correct_answer, core, model_key, mode, custom_prompt)
            if "error" in res:
                log(f"错误: {res['error']}")
            else:
                log(f"模型回答: {res['model_answer']} - {'✓' if res['is_correct'] else '✗'}")
                res['image'] = img_name
                res['question'] = question_text
                res['type'] = q_type
                res['question_index_in_subject'] = q_idx + 1
                res['model_used'] = MODEL_CONFIGS[model_key]["name"]
                res['test_mode'] = mode
                results.append(res)
            time.sleep(REQUEST_INTERVAL)

    task_results[task_id] = results
    update_task_status(task_id, "completed")
    log("知识点测试完成")


# ==================== 数据库的局部测试函数（暂不实现暂停控制） ====================
def run_question_test_db(task_id, subject_key, unit_index, question_index,
                         model_key, mode, custom_prompt=''):
    update_task_status(task_id, "running")
    task_logs[task_id] = []
    def log(msg):
        print(msg)
        task_logs[task_id].append({"time": time.time(), "msg": msg})

    subject_name = os.path.basename(JSON_FILE_MAP[subject_key]['file']).replace('.json', '')
    scenarios = db.get_scenarios_by_category(subject_name)
    if unit_index >= len(scenarios):
        update_task_status(task_id, "completed")
        return
    sc = scenarios[unit_index]
    scenario_id = sc['id']

    files = db.get_scenario_files(scenario_id)
    questions_data = db.get_scenario_questions(scenario_id)

    if question_index >= len(questions_data):
        log("问题索引无效")
        update_task_status(task_id, "completed")
        return

    q_data = questions_data[question_index]
    question_text = q_data['question']
    q_type = q_data['question_type']
    correct_answer = q_data['answer']
    core = q_data.get('core', '') or ''

    default_system_prompt = """
    对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
    按照以下要求回答以下问题：
    1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
    2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
    3. 对于简答题:可以自由回答，输出完整的中文解释。
    """

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
        else:
            log("模式4无可用跨学科数据")

    results = []
    for img_name in files:
        log(f"测试图片 {img_name} 问题: {question_text}")
        res = evaluate_single_question_core(
            subject_key=subject_key,
            image_filename=img_name,
            question_text=question_text,
            question_type=q_type,
            correct_answer=correct_answer,
            core=core,
            model_key=model_key,
            mode=mode,
            system_prompt=system_prompt,
            context_messages=context_messages,
            custom_prompt=custom_prompt
        )
        if "error" in res:
            log(f"错误: {res['error']}")
        else:
            log(f"模型回答: {res['model_answer']} - {'✓' if res['is_correct'] else '✗'}")
            res['image'] = img_name
            res['question'] = question_text
            res['type'] = q_type
            res['model_used'] = MODEL_CONFIGS[model_key]["name"]
            res['test_mode'] = mode
            results.append(res)
        time.sleep(REQUEST_INTERVAL)

    task_results[task_id] = results
    update_task_status(task_id, "completed")
    log("问题测试完成")


def run_knowledge_test_db(task_id, subject_key, unit_index, model_key, mode, custom_prompt=''):
    update_task_status(task_id, "running")
    task_logs[task_id] = []
    def log(msg):
        print(msg)
        task_logs[task_id].append({"time": time.time(), "msg": msg})

    subject_name = os.path.basename(JSON_FILE_MAP[subject_key]['file']).replace('.json', '')
    scenarios = db.get_scenarios_by_category(subject_name)
    if unit_index >= len(scenarios):
        update_task_status(task_id, "completed")
        return
    sc = scenarios[unit_index]
    scenario_id = sc['id']

    files = db.get_scenario_files(scenario_id)
    questions_data = db.get_scenario_questions(scenario_id)

    default_system_prompt = """
    对于收到的题目，首先判断题型，一共有三种题型，选择题、判断题、简答题
    按照以下要求回答以下问题：
    1. 对于选择题:只输出选项字母,例如A,B,C,D或者AB,不要输出任何解释和标点符号，可能会有多选题。
    2. 对于判断题:只输出“对”或“错”，不要输出任何解释和标点符号。
    3. 对于简答题:可以自由回答，输出完整的中文解释。
    """

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
        else:
            log("模式4无可用跨学科数据")

    results = []
    for img_name in files:
        for q_data in questions_data:
            question_text = q_data['question']
            q_type = q_data['question_type']
            correct_answer = q_data['answer']
            core = q_data.get('core', '') or ''
            log(f"图片 {img_name} 题目 {q_data['question_index']+1}: {question_text}")

            res = evaluate_single_question_core(
                subject_key=subject_key,
                image_filename=img_name,
                question_text=question_text,
                question_type=q_type,
                correct_answer=correct_answer,
                core=core,
                model_key=model_key,
                mode=mode,
                system_prompt=system_prompt,
                context_messages=context_messages,
                custom_prompt=custom_prompt
            )
            if "error" in res:
                log(f"错误: {res['error']}")
            else:
                log(f"模型回答: {res['model_answer']} - {'✓' if res['is_correct'] else '✗'}")
                res['image'] = img_name
                res['question'] = question_text
                res['type'] = q_type
                res['question_index_in_subject'] = q_data['question_index'] + 1
                res['model_used'] = MODEL_CONFIGS[model_key]["name"]
                res['test_mode'] = mode
                results.append(res)
            time.sleep(REQUEST_INTERVAL)

    task_results[task_id] = results
    update_task_status(task_id, "completed")
    log("知识点测试完成")