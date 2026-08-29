import os, json, pymysql, re
from datetime import datetime
from envutil import get_env, require_env

# 学科英文→中文、模型英文→中文映射
subject_map = {'physics': '物理', 'biology': '生物', 'chemical': '化学', 'safety': '安全常识'}
model_map = {'Qwen': '通义千问 (Qwen)', 'Gemini': 'Google Gemini', 'Doubao': '火山引擎 (Doubao)'}

# 正则匹配标准文件名：如 "biology_test_mode2_Gemini.json"
pattern = re.compile(r'^(\w+)_test_mode(\d+)_(\w+)\.json$')

db_config = {
    'host': get_env('MYSQL_HOST', 'localhost'),
    'port': int(get_env('MYSQL_PORT', 3306)),
    'user': get_env('MYSQL_USER', 'root'),
    'password': require_env('MYSQL_PASSWORD'),
    'database': get_env('MYSQL_DB', 'evaluation_db'),
    'charset': 'utf8mb4',
}
conn = pymysql.connect(**db_config)
cur = conn.cursor()

results_dir = 'results'  # 实际路径

for fname in os.listdir(results_dir):
    if not fname.endswith('.json'):
        continue
    filepath = os.path.join(results_dir, fname)

    # 检查是否已入库
    cur.execute("SELECT id FROM evaluation_history WHERE result_filename=%s", (fname,))
    if cur.fetchone():
        continue

    # 尝试解析文件名
    m = pattern.match(fname)
    if m:
        subj_eng, mode_str, model_eng = m.groups()
        subject = subject_map.get(subj_eng)
        test_mode = int(mode_str)
        model_name = model_map.get(model_eng)
        if not (subject and model_name):
            subject = model_name = None
    else:
        subject = test_mode = model_name = None

    # 读取 JSON 补全信息
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if model_name is None:
        # 从第一条结果的 model_used 取
        model_name = data['detailed_results'][0].get('model_used', '')
    if test_mode is None:
        test_mode = data['detailed_results'][0].get('test_mode', 1)
    if subject is None:
        # 需要人工介入，或从文件名猜测，这里可以打印出来要求手动指定
        print(f"请手动指定学科: {fname}")
        continue

    # 获取加权准确率百分比
    summary = data.get('summary', {})
    weighted_acc = summary.get('weighted_acc')    # 小数
    if weighted_acc is not None:
        accuracy = round(weighted_acc * 100, 2)
    else:
        accuracy = summary.get('accuracy_percent', 0)

    # 时间处理（用文件修改时间）
    mtime = os.path.getmtime(filepath)
    end_dt = datetime.fromtimestamp(mtime)
    start_dt = datetime.fromtimestamp(mtime - 3600)  # 假设耗时1小时
    start_time = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')

    # 执行插入（使用管理员用户）
    cur.execute(
        "INSERT INTO evaluation_history (user_id, username, start_time, end_time, subject, test_mode, model_name, accuracy, result_filename) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (1, 'admin', start_time, end_time, subject, test_mode, model_name, accuracy, fname)
    )

conn.commit()
cur.close()
conn.close()