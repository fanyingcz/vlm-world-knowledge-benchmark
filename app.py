import os
import re
import json
import time
import uuid
import threading
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from auth import token_required

from config import model_manager, JSON_FILE_MAP, BASE_DIR, MODEL_CONFIGS, RESULTS_DIR
from utils import (
    fix_json_file,
    extract_knowledge_point_name,
    parse_filename,
    load_json,
    analyze_cross_model,
    analyze_cross_subject,
)
from tasks import (
    run_evaluation_with_logs,
    run_evaluation_with_logs_db,
    run_question_test,
    run_question_test_db,
    run_knowledge_test,
    run_knowledge_test_db,
    task_status,
    task_logs,
    task_results,
    task_pre_contexts,
    task_result_file,
    task_info,
    task_control,
    update_task_status,
    _task_lock,
)
import db

app = Flask(__name__)
CORS(app)

# ==================== 模型、学科等基础路由 ====================
@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify(model_manager.get_available_models())

@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    subjects = {}
    for key, info in JSON_FILE_MAP.items():
        subjects[key] = {
            "name": os.path.basename(info['file']).replace('.json', ''),
            "json_file": info['file'],
            "image_folder": info['image_folder']
        }
    return jsonify(subjects)

@app.route('/api/evaluate', methods=['POST'])
@token_required()
def start_evaluation():
    data = request.json
    model_key = data.get('model')
    subject_key = data.get('subject')
    test_mode = int(data.get('mode'))
    max_questions = data.get('max_questions')
    custom_prompt = data.get('custom_prompt')
    data_source = data.get('data_source', 'json')

    if model_key not in model_manager.get_available_models():
        return jsonify({"error": "无效的模型选择"}), 400
    if subject_key not in JSON_FILE_MAP:
        return jsonify({"error": "无效的学科选择"}), 400

    if data_source != 'database':
        json_file = JSON_FILE_MAP[subject_key]["file"]
        image_folder = JSON_FILE_MAP[subject_key]["image_folder"]
        if not os.path.exists(json_file) or not os.path.exists(image_folder):
            return jsonify({"error": "学科文件或图片文件夹不存在"}), 400

    if max_questions == "all" or max_questions is None:
        max_questions = None
    else:
        try:
            max_questions = int(max_questions)
        except:
            max_questions = None

    task_id = str(uuid.uuid4())

    if data_source == 'database':
        thread = threading.Thread(
            target=run_evaluation_with_logs_db,
            args=(task_id, subject_key, test_mode, model_key, max_questions, custom_prompt,
                  g.user_id, g.username)
        )
    else:
        json_file = JSON_FILE_MAP[subject_key]["file"]
        image_folder = JSON_FILE_MAP[subject_key]["image_folder"]
        thread = threading.Thread(
            target=run_evaluation_with_logs,
            args=(task_id, json_file, image_folder, test_mode, model_key, max_questions,
                  custom_prompt, g.user_id, g.username, subject_key)
        )
    thread.daemon = True
    thread.start()

    return jsonify({"task_id": task_id})

@app.route('/api/task/<task_id>/status', methods=['GET'])
def get_task_status(task_id):
    if task_id not in task_status:
        return jsonify({"error": "任务不存在"}), 404

    status = task_status[task_id]
    logs = task_logs.get(task_id, [])
    last_index = request.args.get('last_index', -1, type=int)
    new_logs = logs[last_index+1:] if last_index >= 0 else logs

    response = {
        "status": status,
        "logs": new_logs,
        "total_logs": len(logs)
    }

    if status == "completed":
        results = task_results.get(task_id, [])
        total = len(results)
        correct = sum(1 for r in results if r.get("is_correct", False))
        accuracy = round(correct / total * 100, 2) if total > 0 else 0.0

        weights = {"简答题": 4, "选择题": 2, "判断题": 1}
        total_weight = sum(weights.get(r.get("type"), 0) for r in results)
        correct_weight = sum(weights.get(r.get("type"), 0) for r in results if r.get("is_correct", False))
        weighted_accuracy = round(correct_weight / total_weight * 100, 2) if total_weight > 0 else 0.0

        response["summary"] = {
            "total": total,
            "correct": correct,
            "incorrect": total - correct,
            "accuracy": accuracy,
            "weighted_accuracy": weighted_accuracy
        }
        response["result_file"] = task_result_file.get(task_id, "")

    return jsonify(response)

@app.route('/api/save_result', methods=['POST'])
@token_required()
def save_result():
    data = request.json
    task_id = data.get('task_id')
    filename = data.get('filename', '').strip()

    if not task_id or task_id not in task_results:
        return jsonify({"error": "无效的任务ID"}), 400
    if not filename:
        return jsonify({"error": "文件名不能为空"}), 400
    if not re.match(r'^[\w\u4e00-\u9fff.-]+$', filename):
        return jsonify({"error": "文件名包含非法字符"}), 400
    if not filename.lower().endswith('.json'):
        filename += '.json'

    results_dir = os.path.join(BASE_DIR, 'results')
    os.makedirs(results_dir, exist_ok=True)
    save_path = os.path.join(results_dir, filename)
    if os.path.exists(save_path):
        return jsonify({"error": "文件已存在，请更换文件名"}), 409

    try:
        results = task_results[task_id]
        pre_contexts = task_pre_contexts.get(task_id, [])
        output_data = {
            "summary": {
                "total_questions": len(results),
                "correct_count": sum(1 for r in results if r.get("is_correct", False)),
                "incorrect_count": sum(1 for r in results if not r.get("is_correct", False)),
                "accuracy_percent": round(
                    sum(1 for r in results if r.get("is_correct", False)) / len(results) * 100, 2
                ) if results else 0.0
            },
            "pre_question_contexts": pre_contexts,
            "detailed_results": results,
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        task_result_file[task_id] = filename

        # 自动修正
        try:
            fixed_cnt, total_q, correct_q, acc = fix_json_file(save_path)
            fix_msg = f"结果已保存并自动修正：修正了 {fixed_cnt} 条简答题的判定，当前总题数 {total_q}，正确 {correct_q}，正确率 {acc}%"
            if task_id in task_logs:
                task_logs[task_id].append({"time": time.time(), "msg": fix_msg})
        except Exception as fix_err:
            err_msg = f"自动修正失败: {str(fix_err)}"
            if task_id in task_logs:
                task_logs[task_id].append({"time": time.time(), "msg": err_msg})
            with open(save_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            total_q = len(json_data.get("detailed_results", []))
            correct_q = sum(1 for r in json_data.get("detailed_results", []) if r.get("is_correct", False))
            acc = round(correct_q / total_q * 100, 2) if total_q > 0 else 0.0

        # 加权准确率
        with open(save_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        weights = {"简答题": 4, "选择题": 2, "判断题": 1}
        total_weight = 0
        correct_weight = 0
        for item in json_data.get("detailed_results", []):
            w = weights.get(item.get("type"), 0)
            total_weight += w
            if item.get("is_correct", False):
                correct_weight += w
        weighted_acc_decimal = round(correct_weight / total_weight, 4) if total_weight > 0 else 0.0
        weighted_acc_percent = round(weighted_acc_decimal * 100, 2)
        if "summary" not in json_data:
            json_data["summary"] = {}
        json_data["summary"]["weighted_acc"] = weighted_acc_decimal
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # 写入评测历史
        info = task_info.get(task_id, {})
        start_time = datetime.fromtimestamp(info.get('start_time', time.time()))
        end_time = datetime.now()
        subject_name = os.path.splitext(os.path.basename(JSON_FILE_MAP[info['subject_key']]['file']))[0]
        model_name = MODEL_CONFIGS[info['model_key']]['name']
        accuracy_val = weighted_acc_percent

        db.execute(
            """INSERT INTO evaluation_history 
               (user_id, username, start_time, end_time, subject, test_mode, model_name, accuracy, result_filename)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (g.user_id, g.username, start_time, end_time, subject_name,
             info['test_mode'], model_name, accuracy_val, filename)
        )

        return jsonify({
            "success": True,
            "filename": filename,
            "summary": {
                "total": total_q,
                "correct": correct_q,
                "incorrect": total_q - correct_q,
                "accuracy": acc,
                "weighted_accuracy": weighted_acc_percent
            }
        })
    except Exception as e:
        return jsonify({"error": f"保存文件失败: {str(e)}"}), 500

@app.route('/api/evaluation-history', methods=['GET'])
@token_required()
def get_evaluation_history():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit

    subject = request.args.get('subject', '').strip()
    model_name = request.args.get('model_name', '').strip()
    test_mode = request.args.get('test_mode', type=int)
    filename = request.args.get('filename', '').strip()

    sort_by = request.args.get('sort_by', '').strip()
    sort_order = request.args.get('sort_order', 'descending').strip()

    base_sql = "FROM evaluation_history WHERE 1=1"
    params = []

    if g.role != 'admin':
        base_sql += " AND user_id = %s"
        params.append(g.user_id)

    if subject:
        base_sql += " AND subject = %s"
        params.append(subject)
    if model_name:
        base_sql += " AND model_name = %s"
        params.append(model_name)
    if test_mode is not None:
        base_sql += " AND test_mode = %s"
        params.append(test_mode)
    if filename:
        base_sql += " AND result_filename LIKE %s"
        params.append('%' + filename + '%')

    allowed_sort_columns = {
        'user': 'username',
        'subject': 'subject',
        'test_mode': 'test_mode',
        'accuracy': 'accuracy',
        'start_time': 'start_time',
        'end_time': 'end_time',
        'model': 'model_name',
        'filename': 'result_filename'
    }
    order_clause = ''
    if sort_by in allowed_sort_columns:
        column = allowed_sort_columns[sort_by]
        direction = 'ASC' if sort_order.lower() == 'ascending' else 'DESC'
        order_clause = f" ORDER BY {column} {direction}"
    else:
        order_clause = " ORDER BY created_at DESC"

    count_sql = "SELECT COUNT(*) AS total " + base_sql
    total = db.query_one(count_sql, tuple(params))['total']

    data_sql = "SELECT * " + base_sql + order_clause + " LIMIT %s OFFSET %s"
    records = db.query_all(data_sql, tuple(params + [limit, offset]))

    for r in records:
        r['start_time'] = r['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        r['end_time'] = r['end_time'].strftime('%Y-%m-%d %H:%M:%S')
        r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({
        'total': total,
        'page': page,
        'limit': limit,
        'records': records
    })

@app.route('/api/evaluation-history/<int:record_id>', methods=['DELETE'])
@token_required(required_roles=['admin'])
def delete_evaluation_history(record_id):
    record = db.query_one("SELECT id FROM evaluation_history WHERE id = %s", (record_id,))
    if not record:
        return jsonify({"error": "记录不存在"}), 404
    db.execute("DELETE FROM evaluation_history WHERE id = %s", (record_id,))
    return jsonify({"message": "删除成功"}), 200

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        files = request.files.getlist('files')
        if not files:
            return jsonify({'success': False, 'error': '未上传任何文件'}), 400

        analysis_type = request.form.get('analysis_type')
        if analysis_type not in ('cross-model', 'cross-subject'):
            return jsonify({'success': False, 'error': '无效的分析模式'}), 400

        file_data = []
        for f in files:
            subject, test_mode, model = parse_filename(f.filename)
            data = load_json(f)
            file_data.append({
                'subject': subject,
                'test_mode': test_mode,
                'model': model,
                'summary': data.get('summary', {}),
                'detailed_results': data.get('detailed_results', [])
            })

        if analysis_type == 'cross-model':
            subjects = set(d['subject'] for d in file_data)
            if len(subjects) > 1:
                return jsonify({'success': False, 'error': '多模型分析要求所有文件属于同一学科'}), 400
            result_data = analyze_cross_model(file_data)
        else:
            models_set = set(d['model'] for d in file_data)
            if len(models_set) > 1:
                return jsonify({'success': False, 'error': '单一模型分析要求所有文件属于同一模型'}), 400
            result_data = analyze_cross_subject(file_data)

        analysis_dir = RESULTS_DIR
        os.makedirs(analysis_dir, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        if analysis_type == 'cross-model':
            subject_str = '_'.join(sorted(subjects))
            filename = f"cross_model_{subject_str}_{timestamp}.json"
        else:
            safe_model = re.sub(r'[\\/*?:"<>| ]', '_', result_data['model'])
            filename = f"cross_subject_{safe_model}_{timestamp}.json"
        filepath = os.path.join(analysis_dir, filename)
        saved_data = {
            'analysis_type': analysis_type,
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'result': result_data
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(saved_data, f, ensure_ascii=False, indent=2)

        return jsonify({
            'success': True,
            'data': result_data,
            'saved_file': filename,
            'saved_path': filepath
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/knowledge_points', methods=['GET'])
def get_knowledge_points():
    subject_key = request.args.get('subject')
    source = request.args.get('source', 'json')

    if not subject_key or subject_key not in JSON_FILE_MAP:
        return jsonify({"error": "无效的学科"}), 400

    if source == 'database':
        subject_name = os.path.basename(JSON_FILE_MAP[subject_key]['file']).replace('.json', '')
        scenarios = db.get_scenarios_by_category(subject_name)
        knowledge_points = []
        for idx, sc in enumerate(scenarios):
            files = db.get_scenario_files(sc['id'])
            questions_data = db.get_scenario_questions(sc['id'])
            questions = [q['question'] for q in questions_data]
            question_types = [q['question_type'] for q in questions_data]
            answers = [q['answer'] for q in questions_data]
            cores = [q.get('core', '') or '' for q in questions_data]
            name = extract_knowledge_point_name(files) if files else f"场景{sc['id']}"
            knowledge_points.append({
                "name": name,
                "unit_index": idx,
                "files": files,
                "questions": questions,
                "question_type": question_types,
                "answers": answers,
                "cores": cores,
                "has_pre_question": bool(sc.get('pre_question') and sc.get('pre_answer')),
                "pre_question": sc.get('pre_question', ''),
                "pre_answer": sc.get('pre_answer', ''),
            })
        return jsonify({"knowledge_points": knowledge_points})

    json_file = JSON_FILE_MAP[subject_key]["file"]
    if not os.path.exists(json_file):
        return jsonify({"error": "学科文件不存在"}), 404

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    knowledge_points = []
    for idx, unit in enumerate(data):
        name = extract_knowledge_point_name(unit.get('files', []))
        knowledge_points.append({
            "name": name,
            "unit_index": idx,
            "files": unit.get('files', []),
            "questions": unit.get('questions', []),
            "question_type": unit.get('question_type', []),
            "answers": unit.get('answers', []),
            "cores": unit.get('core', []),
            "has_pre_question": bool(unit.get('pre_question') and unit.get('pre_answer')),
            "pre_question": unit.get('pre_question', ''),
            "pre_answer": unit.get('pre_answer', ''),
        })

    return jsonify({"knowledge_points": knowledge_points})

@app.route('/api/test_single', methods=['POST'])
def test_single():
    data = request.json
    required = ['subject', 'unit_index', 'image', 'question', 'question_type', 'correct_answer', 'model', 'mode']
    for field in required:
        if field not in data:
            return jsonify({"error": f"缺少参数: {field}"}), 400

    data_source = data.get('data_source', 'json')
    try:
        if data_source == 'database':
            from utils import evaluate_single_question_db
            res = evaluate_single_question_db(
                subject_key=data['subject'],
                unit_index=data['unit_index'],
                image_filename=data['image'],
                question_text=data['question'],
                question_type=data['question_type'],
                correct_answer=data['correct_answer'],
                core=data.get('core', ''),
                model_key=data['model'],
                mode=int(data['mode']),
                custom_prompt=data.get('custom_prompt', '')
            )
        else:
            from utils import evaluate_single_question
            res = evaluate_single_question(
                subject_key=data['subject'],
                unit_index=data['unit_index'],
                image_filename=data['image'],
                question_text=data['question'],
                question_type=data['question_type'],
                correct_answer=data['correct_answer'],
                core=data.get('core', ''),
                model_key=data['model'],
                mode=int(data['mode']),
                custom_prompt=data.get('custom_prompt', '')
            )

        if "error" in res:
            return jsonify({"success": False, "error": res["error"]}), 400
        return jsonify({"success": True, "result": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/test_question', methods=['POST'])
def start_question_test():
    data = request.json
    task_id = str(uuid.uuid4())
    data_source = data.get('data_source', 'json')

    if data_source == 'database':
        thread = threading.Thread(
            target=run_question_test_db,
            args=(task_id, data['subject'], data['unit_index'], data['question_index'],
                  data['model'], int(data['mode']), data.get('custom_prompt', ''))
        )
    else:
        thread = threading.Thread(
            target=run_question_test,
            args=(task_id, data['subject'], data['unit_index'], data['question_index'],
                  data['model'], int(data['mode']), data.get('custom_prompt', ''))
        )
    thread.daemon = True
    thread.start()
    return jsonify({"task_id": task_id})

@app.route('/api/test_knowledge', methods=['POST'])
def start_knowledge_test():
    data = request.json
    task_id = str(uuid.uuid4())
    data_source = data.get('data_source', 'json')

    if data_source == 'database':
        thread = threading.Thread(
            target=run_knowledge_test_db,
            args=(task_id, data['subject'], data['unit_index'],
                  data['model'], int(data['mode']), data.get('custom_prompt', ''))
        )
    else:
        thread = threading.Thread(
            target=run_knowledge_test,
            args=(task_id, data['subject'], data['unit_index'],
                  data['model'], int(data['mode']), data.get('custom_prompt', ''))
        )
    thread.daemon = True
    thread.start()
    return jsonify({"task_id": task_id})

@app.route('/api/chart-data', methods=['GET'])
@token_required()
def get_chart_data():
    if g.role == 'admin':
        records = db.query_all(
            "SELECT subject, model_name, test_mode, accuracy FROM evaluation_history"
        )
    else:
        records = db.query_all(
            "SELECT subject, model_name, test_mode, accuracy FROM evaluation_history WHERE user_id = %s",
            (g.user_id,)
        )

    mode_acc = {}
    mode_cnt = {}
    model_acc = {}
    model_cnt = {}
    subject_data = {}

    for r in records:
        subj = r['subject']
        mdl = r['model_name']
        mode = str(r['test_mode'])
        acc = r['accuracy']

        mode_acc[mode] = mode_acc.get(mode, 0) + acc
        mode_cnt[mode] = mode_cnt.get(mode, 0) + 1

        model_acc[mdl] = model_acc.get(mdl, 0) + acc
        model_cnt[mdl] = model_cnt.get(mdl, 0) + 1

        if subj not in subject_data:
            subject_data[subj] = {
                'mode_acc': {}, 'mode_cnt': {},
                'model_acc': {}, 'model_cnt': {}
            }
        sd = subject_data[subj]
        sd['mode_acc'][mode] = sd['mode_acc'].get(mode, 0) + acc
        sd['mode_cnt'][mode] = sd['mode_cnt'].get(mode, 0) + 1
        sd['model_acc'][mdl] = sd['model_acc'].get(mdl, 0) + acc
        sd['model_cnt'][mdl] = sd['model_cnt'].get(mdl, 0) + 1

    def average(acc_dict, cnt_dict):
        return {k: round(acc_dict[k] / cnt_dict[k], 2) for k in acc_dict}

    overall_mode = average(mode_acc, mode_cnt)
    overall_model = average(model_acc, model_cnt)

    subjects_res = {}
    for subj, data in subject_data.items():
        subjects_res[subj] = {
            'mode': average(data['mode_acc'], data['mode_cnt']),
            'model': average(data['model_acc'], data['model_cnt'])
        }

    overall_mode = dict(sorted(overall_mode.items(), key=lambda x: int(x[0])))
    overall_model = dict(sorted(overall_model.items()))

    return jsonify({
        'overall_mode': overall_mode,
        'overall_model': overall_model,
        'subjects': subjects_res
    })

# ==================== 数据集管理 API ====================
@app.route('/api/datasets', methods=['GET'])
@token_required(required_roles=['admin'])
def list_datasets():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    subject = request.args.get('subject', '').strip()
    offset = (page - 1) * limit

    base_sql = "FROM scenarios WHERE 1=1"
    params = []
    if subject:
        base_sql += " AND category = %s"
        params.append(subject)

    count_sql = "SELECT COUNT(*) AS total " + base_sql
    total = db.query_one(count_sql, tuple(params))['total']

    data_sql = "SELECT * " + base_sql + " ORDER BY id DESC LIMIT %s OFFSET %s"
    records = db.query_all(data_sql, tuple(params + [limit, offset]))

    return jsonify({'total': total, 'page': page, 'limit': limit, 'records': records})

@app.route('/api/datasets/<int:scenario_id>', methods=['GET'])
@token_required(required_roles=['admin'])
def get_dataset_detail(scenario_id):
    scenario = db.query_one("SELECT * FROM scenarios WHERE id = %s", (scenario_id,))
    if not scenario:
        return jsonify({'error': '场景不存在'}), 404
    files_rows = db.query_all(
        "SELECT id, file_name FROM scenario_files WHERE scenario_id = %s ORDER BY id",
        (scenario_id,))
    scenario['files'] = [{'id': r['id'], 'file_name': r['file_name']} for r in files_rows]
    questions = db.get_scenario_questions(scenario_id)
    scenario['questions'] = questions
    return jsonify(scenario)

@app.route('/api/datasets', methods=['POST'])
@token_required(required_roles=['admin'])
def create_dataset():
    data = request.get_json()
    category = data.get('category', '').strip()
    pre_question = data.get('pre_question', '').strip()
    pre_answer = data.get('pre_answer', '').strip()
    cot = data.get('cot', '').strip()

    if not category:
        return jsonify({'error': '学科不能为空'}), 400

    db.execute(
        "INSERT INTO scenarios (category, pre_question, pre_answer, cot) VALUES (%s, %s, %s, %s)",
        (category, pre_question, pre_answer, cot)
    )
    new_id = db.query_one("SELECT LAST_INSERT_ID() AS id")['id']
    return jsonify({'message': '创建成功', 'id': new_id}), 201

@app.route('/api/datasets/<int:scenario_id>', methods=['PUT'])
@token_required(required_roles=['admin'])
def update_dataset(scenario_id):
    data = request.get_json()
    scenario = db.query_one("SELECT id FROM scenarios WHERE id = %s", (scenario_id,))
    if not scenario:
        return jsonify({'error': '场景不存在'}), 404

    fields = []
    params = []
    for key in ['category', 'pre_question', 'pre_answer', 'cot']:
        if key in data:
            fields.append(f"{key} = %s")
            params.append(data[key])
    if not fields:
        return jsonify({'error': '无更新字段'}), 400

    sql = f"UPDATE scenarios SET {', '.join(fields)} WHERE id = %s"
    params.append(scenario_id)
    db.execute(sql, tuple(params))
    return jsonify({'message': '更新成功'})

@app.route('/api/datasets/<int:scenario_id>', methods=['DELETE'])
@token_required(required_roles=['admin'])
def delete_dataset(scenario_id):
    scenario = db.query_one("SELECT id FROM scenarios WHERE id = %s", (scenario_id,))
    if not scenario:
        return jsonify({'error': '场景不存在'}), 404
    db.execute("DELETE FROM scenarios WHERE id = %s", (scenario_id,))
    return jsonify({'message': '删除成功'})

@app.route('/api/datasets/<int:scenario_id>/files', methods=['POST'])
@token_required(required_roles=['admin'])
def add_scenario_file(scenario_id):
    data = request.get_json()
    file_name = data.get('file_name', '').strip()
    if not file_name:
        return jsonify({'error': '文件名不能为空'}), 400
    sc = db.query_one("SELECT id FROM scenarios WHERE id = %s", (scenario_id,))
    if not sc:
        return jsonify({'error': '场景不存在'}), 404
    db.execute("INSERT INTO scenario_files (scenario_id, file_name) VALUES (%s, %s)",
               (scenario_id, file_name))
    return jsonify({'message': '图片添加成功'}), 201

@app.route('/api/datasets/files/<int:file_id>', methods=['DELETE'])
@token_required(required_roles=['admin'])
def delete_scenario_file(file_id):
    db.execute("DELETE FROM scenario_files WHERE id = %s", (file_id,))
    return jsonify({'message': '图片删除成功'})

@app.route('/api/datasets/<int:scenario_id>/questions', methods=['POST'])
@token_required(required_roles=['admin'])
def add_scenario_question(scenario_id):
    data = request.get_json()
    question_text = data.get('question', '').strip()
    question_type = data.get('question_type', '').strip()
    answer = data.get('answer', '').strip()
    core = data.get('core', '').strip()
    if not question_text or not question_type or not answer:
        return jsonify({'error': '问题、题型、答案不能为空'}), 400

    existing = db.query_all(
        "SELECT question_index FROM scenario_questions WHERE scenario_id = %s ORDER BY question_index",
        (scenario_id,))
    next_index = 0
    if existing:
        next_index = existing[-1]['question_index'] + 1

    db.execute(
        "INSERT INTO scenario_questions (scenario_id, question_index, question, question_type, answer, core) VALUES (%s, %s, %s, %s, %s, %s)",
        (scenario_id, next_index, question_text, question_type, answer, core))
    return jsonify({'message': '问题添加成功', 'question_index': next_index}), 201

@app.route('/api/datasets/questions/<int:question_id>', methods=['PUT'])
@token_required(required_roles=['admin'])
def update_scenario_question(question_id):
    data = request.get_json()
    fields = []
    params = []
    for key in ['question', 'question_type', 'answer', 'core']:
        if key in data:
            fields.append(f"{key} = %s")
            params.append(data[key])
    if not fields:
        return jsonify({'error': '无更新字段'}), 400
    sql = f"UPDATE scenario_questions SET {', '.join(fields)} WHERE id = %s"
    params.append(question_id)
    db.execute(sql, tuple(params))
    return jsonify({'message': '问题更新成功'})

@app.route('/api/datasets/questions/<int:question_id>', methods=['DELETE'])
@token_required(required_roles=['admin'])
def delete_scenario_question(question_id):
    db.execute("DELETE FROM scenario_questions WHERE id = %s", (question_id,))
    return jsonify({'message': '问题删除成功'})

@app.route('/api/subjects-list', methods=['GET'])
@token_required(required_roles=['admin'])
def get_subjects_list():
    rows = db.query_all("SELECT DISTINCT category FROM scenarios ORDER BY category")
    subjects = [r['category'] for r in rows]
    return jsonify(subjects)

# ==================== 新增：暂停 / 继续 / 强制结束 ====================
@app.route('/api/task/<task_id>/pause', methods=['POST'])
@token_required()
def pause_task(task_id):
    if task_id not in task_status:
        return jsonify({"error": "任务不存在"}), 404
    with _task_lock:
        if task_status[task_id] in ('completed', 'stopped'):
            return jsonify({"error": "任务已结束"}), 400
        if task_status[task_id] == 'paused':
            return jsonify({"message": "任务已是暂停状态"})
        if task_id in task_control:
            task_control[task_id]['pause_requested'] = True
            return jsonify({"success": True, "message": "暂停指令已下达"})
        return jsonify({"error": "任务控制数据缺失"}), 500

@app.route('/api/task/<task_id>/resume', methods=['POST'])
@token_required()
def resume_task(task_id):
    if task_id not in task_status:
        return jsonify({"error": "任务不存在"}), 404
    with _task_lock:
        if task_status[task_id] != 'paused':
            return jsonify({"error": "任务未处于暂停状态"}), 400

        # 检查控制对象是否存在，避免恢复已丢失的线程
        if task_id not in task_control:
            update_task_status(task_id, 'error')
            return jsonify({"error": "任务控制已丢失，无法继续"}), 500

        ctrl = task_control[task_id]
        # 双重保险：如果事件已经 set，不重复操作
        if not ctrl['pause_event'].is_set():
            ctrl['pause_event'].set()
        ctrl['pause_requested'] = False
        update_task_status(task_id, 'running')

    # 记录日志，方便排查
    print(f"[TASK] {task_id} 已由用户恢复继续。")
    if task_id in task_logs:
        task_logs[task_id].append({"time": time.time(), "msg": "任务已由用户手动继续"})
    return jsonify({"success": True, "message": "任务已继续"})

@app.route('/api/task/<task_id>/stop', methods=['POST'])
@token_required()
def stop_task(task_id):
    if task_id not in task_status:
        return jsonify({"error": "任务不存在"}), 404
    with _task_lock:
        if task_status[task_id] in ('completed', 'stopped'):
            return jsonify({"error": "任务已结束"}), 400
        if task_id in task_control:
            task_control[task_id]['stop_requested'] = True
            task_control[task_id]['pause_event'].set()   # 唤醒可能的暂停等待
    return jsonify({"success": True, "message": "停止指令已下达"})

# 注册认证蓝图
from auth import auth_bp
app.register_blueprint(auth_bp)

if __name__ == '__main__':
    from db import init_db
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)