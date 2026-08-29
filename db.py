import os
import pymysql
from pymysql.cursors import DictCursor
from envutil import get_env, require_env

# MYSQL_PASSWORD is mandatory: the app refuses to start without it rather than
# silently falling back to a hardcoded credential.
DB_CONFIG = {
    'host': get_env('MYSQL_HOST', 'localhost'),
    'port': int(get_env('MYSQL_PORT', 3306)),
    'user': get_env('MYSQL_USER', 'root'),
    'password': require_env('MYSQL_PASSWORD'),
    'database': get_env('MYSQL_DB', 'evaluation_db'),
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}

def get_connection():
    return pymysql.connect(**DB_CONFIG)

def query_one(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        conn.close()

def execute(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
        conn.commit()
    finally:
        conn.close()

def query_all(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    finally:
        conn.close()

def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role ENUM('visitor', 'regular', 'admin') DEFAULT 'regular',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    username VARCHAR(50) NOT NULL,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    subject VARCHAR(50) NOT NULL,
                    test_mode INT NOT NULL,
                    model_name VARCHAR(100) NOT NULL,
                    accuracy DECIMAL(5,2) NOT NULL,
                    result_filename VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()

def get_scenarios_by_category(category):
    """按学科获取所有场景，按ID排序"""
    sql = "SELECT id, category, pre_question, pre_answer, cot FROM scenarios WHERE category = %s ORDER BY id"
    return query_all(sql, (category,))

def get_scenario_files(scenario_id):
    """获取某个场景的所有图片文件名"""
    sql = "SELECT file_name FROM scenario_files WHERE scenario_id = %s ORDER BY id"
    rows = query_all(sql, (scenario_id,))
    return [row['file_name'] for row in rows]

def get_scenario_questions(scenario_id):
    """获取某个场景的所有题目，按 question_index 排序"""
    sql = "SELECT question_index, question, question_type, answer, core FROM scenario_questions WHERE scenario_id = %s ORDER BY question_index"
    return query_all(sql, (scenario_id,))