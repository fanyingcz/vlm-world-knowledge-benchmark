import json
import os
import sys
import glob
from db import get_connection, execute

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS scenarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(20) NOT NULL COMMENT '学科',
    pre_question TEXT COMMENT '前置问题',
    pre_answer TEXT COMMENT '前置答案',
    cot TEXT COMMENT '推理思路(COT)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景主表';

CREATE TABLE IF NOT EXISTS scenario_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scenario_id INT NOT NULL,
    file_name VARCHAR(255) NOT NULL COMMENT '图片文件名',
    FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景关联图片文件表';

CREATE TABLE IF NOT EXISTS scenario_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scenario_id INT NOT NULL,
    question_index INT NOT NULL COMMENT '问题序号(从0开始)',
    question TEXT NOT NULL COMMENT '问题内容',
    question_type VARCHAR(20) NOT NULL COMMENT '题型(简答题/选择题/判断题)',
    answer TEXT NOT NULL COMMENT '答案',
    core VARCHAR(255) DEFAULT NULL COMMENT '核心知识点',
    FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景包含的具体问题表';
"""

def create_tables():
    """创建所需数据表（如不存在）"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 逐条执行建表语句，不支持多语句时需拆分
            for statement in CREATE_TABLES_SQL.strip().split(';'):
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)
            conn.commit()
            print("数据库表创建/确认完成。")
    except Exception as e:
        conn.rollback()
        print(f"建表失败: {e}")
        raise
    finally:
        conn.close()

def import_json_file(filepath):
    """导入单个JSON文件"""
    print(f"正在处理文件: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        print(f"警告: 文件 {filepath} 的顶层结构不是数组，跳过。")
        return 0
    
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    print(f"跳过第 {idx} 项，格式错误。")
                    continue
                
                category = item.get('category', '未知')
                pre_question = item.get('pre_question', '')
                pre_answer = item.get('pre_answer', '')
                cot = item.get('COT', '')
                
                # 插入主表
                cursor.execute(
                    "INSERT INTO scenarios (category, pre_question, pre_answer, cot) VALUES (%s, %s, %s, %s)",
                    (category, pre_question, pre_answer, cot)
                )
                scenario_id = cursor.lastrowid
                
                # 插入图片文件列表
                files = item.get('files', [])
                if isinstance(files, list):
                    for fname in files:
                        if fname:
                            cursor.execute(
                                "INSERT INTO scenario_files (scenario_id, file_name) VALUES (%s, %s)",
                                (scenario_id, fname)
                            )
                
                # 插入问题列表，假设 questions, question_type, answers, core 长度一致
                questions = item.get('questions', [])
                question_types = item.get('question_type', [])
                answers = item.get('answers', [])
                cores = item.get('core', [])
                
                # 保证长度为最大，用空字符串填充缺失项
                max_len = max(len(questions), len(question_types), len(answers), len(cores))
                for i in range(max_len):
                    q = questions[i] if i < len(questions) else ''
                    qt = question_types[i] if i < len(question_types) else ''
                    ans = answers[i] if i < len(answers) else ''
                    cor = cores[i] if i < len(cores) else ''
                    cursor.execute(
                        "INSERT INTO scenario_questions (scenario_id, question_index, question, question_type, answer, core) VALUES (%s, %s, %s, %s, %s, %s)",
                        (scenario_id, i, q, qt, ans, cor)
                    )
        conn.commit()
        print(f"成功导入 {len(data)} 个场景。")
        return len(data)
    except Exception as e:
        conn.rollback()
        print(f"导入过程中出错: {e}")
        raise
    finally:
        conn.close()

def main():
    # 默认在当前目录下查找所有以 "常识" 或 "物理" 等学科命名的 JSON 文件
    # 也可以直接指定文件列表，或通过命令行参数传递
    if len(sys.argv) > 1:
        json_files = sys.argv[1:]
    else:
        # 自动搜索常见的四个学科文件，可修改扩展名匹配规则
        categories = ['物理', '化学', '生物', '安全常识']
        json_files = []
        for cat in categories:
            # 匹配如 "物理.json", "物理-xxx.json" 等
            pattern = f"{cat}*.json"
            json_files.extend(glob.glob(pattern))
        if not json_files:
            print("未找到任何JSON文件。请将文件放在当前目录，或通过命令行指定文件路径。")
            print("用法: python import_data.py [file1.json file2.json ...]")
            sys.exit(1)
    
    print(f"待导入文件列表: {json_files}")
    create_tables()
    
    total = 0
    for f in json_files:
        if os.path.isfile(f):
            total += import_json_file(f)
        else:
            print(f"文件不存在: {f}")
    print(f"全部导入完成，共导入 {total} 个场景。")

if __name__ == "__main__":
    main()