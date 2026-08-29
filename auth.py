import os
import jwt
import bcrypt
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from functools import wraps
import db

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# JWT 配置
SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-in-production')
JWT_EXPIRATION_HOURS = 24

# 角色层级
ROLE_HIERARCHY = {'visitor': 0, 'regular': 1, 'admin': 2}


def generate_token(user_id, role, username=None):
    payload = {
        'user_id': user_id,
        'role': role,
        'username': username,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def token_required(required_roles=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not token:
                return jsonify({'error': '未提供认证令牌'}), 401
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
                user_id = payload['user_id']
                role = payload['role']
                g.user_id = user_id
                g.role = role
                g.username = payload.get('username', f'user_{user_id}')
                # 游客虚拟用户
                if user_id == -1:
                    g.role = 'visitor'
                else:
                    user = db.query_one("SELECT id, role FROM users WHERE id = %s", (user_id,))
                    if not user:
                        return jsonify({'error': '用户不存在'}), 401
                    g.role = user['role']
                # 权限检查
                if required_roles:
                    user_level = ROLE_HIERARCHY.get(g.role, -1)
                    required_level = max(ROLE_HIERARCHY.get(r, -1) for r in required_roles)
                    if user_level < required_level:
                        return jsonify({'error': '权限不足'}), 403
                return f(*args, **kwargs)
            except jwt.ExpiredSignatureError:
                return jsonify({'error': '令牌已过期'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'error': '无效的令牌'}), 401
        return decorated
    return decorator


# ---------- 注册 ----------
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'regular')

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 3 or len(password) < 6:
        return jsonify({'error': '用户名至少3位，密码至少6位'}), 400
    if role not in ('visitor', 'regular'):
        return jsonify({'error': '只允许注册游客或正式用户'}), 400

    existing = db.query_one("SELECT id FROM users WHERE username = %s", (username,))
    if existing:
        return jsonify({'error': '用户名已存在'}), 409

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, password_hash, role)
    )
    return jsonify({'message': '注册成功'}), 201


# ---------- 登录 ----------
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = db.query_one("SELECT id, password_hash, role FROM users WHERE username = %s", (username,))
    if not user:
        return jsonify({'error': '用户名或密码错误'}), 401

    try:
        if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return jsonify({'error': '用户名或密码错误'}), 401
    except ValueError:
        return jsonify({'error': '用户名或密码错误'}), 401

    token = generate_token(user['id'], user['role'], username)
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'username': username,
            'role': user['role']
        }
    }), 200


# ---------- 游客登录 ----------
@auth_bp.route('/guest-login', methods=['POST'])
def guest_login():
    guest_username = f"guest_{uuid.uuid4().hex[:8]}"
    token = generate_token(-1, 'visitor', guest_username)
    return jsonify({
        'token': token,
        'user': {
            'id': -1,
            'username': guest_username,
            'role': 'visitor'
        }
    }), 200


# ---------- 获取当前用户 ----------
@auth_bp.route('/me', methods=['GET'])
@token_required()
def get_current_user():
    if g.user_id == -1:
        return jsonify({'user': {'id': -1, 'username': '游客', 'role': 'visitor'}}), 200
    user = db.query_one("SELECT id, username, role, created_at FROM users WHERE id = %s", (g.user_id,))
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    return jsonify({'user': user}), 200


# ---------- 管理员：用户列表（支持搜索） ----------
@auth_bp.route('/users', methods=['GET'])
@token_required(required_roles=['admin'])
def list_users():
    search = request.args.get('search', '').strip()
    if search:
        users = db.query_all(
            "SELECT id, username, role, created_at FROM users WHERE username LIKE %s ORDER BY id",
            ('%' + search + '%',)
        )
    else:
        users = db.query_all("SELECT id, username, role, created_at FROM users ORDER BY id")
    return jsonify({'users': users}), 200


# ---------- 管理员：创建用户 ----------
@auth_bp.route('/users', methods=['POST'])
@token_required(required_roles=['admin'])
def create_user():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'regular')

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 3 or len(password) < 6:
        return jsonify({'error': '用户名至少3位，密码至少6位'}), 400
    if role not in ('visitor', 'regular', 'admin'):
        return jsonify({'error': '无效的角色'}), 400

    existing = db.query_one("SELECT id FROM users WHERE username = %s", (username,))
    if existing:
        return jsonify({'error': '用户名已存在'}), 409

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, password_hash, role)
    )
    return jsonify({'message': '用户创建成功'}), 201


# ---------- 管理员：更新用户（用户名和/或角色） ----------
@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@token_required(required_roles=['admin'])
def update_user(user_id):
    data = request.get_json()
    username = data.get('username', '').strip()
    new_role = data.get('role')

    if not username and not new_role:
        return jsonify({'error': '没有要更新的字段'}), 400
    if user_id == g.user_id:
        return jsonify({'error': '不能修改自己的信息'}), 403

    # 检查用户名唯一性
    if username:
        existing = db.query_one(
            "SELECT id FROM users WHERE username = %s AND id != %s", (username, user_id))
        if existing:
            return jsonify({'error': '用户名已被其他用户使用'}), 409
        if len(username) < 3:
            return jsonify({'error': '用户名至少3位'}), 400

    if new_role and new_role not in ('visitor', 'regular', 'admin'):
        return jsonify({'error': '无效的角色'}), 400

    # 动态构建SQL
    fields = []
    params = []
    if username:
        fields.append("username = %s")
        params.append(username)
    if new_role:
        fields.append("role = %s")
        params.append(new_role)

    sql = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
    params.append(user_id)
    db.execute(sql, tuple(params))
    return jsonify({'message': '用户信息已更新'}), 200


# ---------- 管理员：修改角色（保留原接口，兼容旧调用） ----------
@auth_bp.route('/users/<int:user_id>/role', methods=['PUT'])
@token_required(required_roles=['admin'])
def change_user_role(user_id):
    data = request.get_json()
    new_role = data.get('role')
    if new_role not in ('visitor', 'regular', 'admin'):
        return jsonify({'error': '无效的角色'}), 400
    if user_id == g.user_id:
        return jsonify({'error': '不能修改自己的角色'}), 403
    db.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
    return jsonify({'message': '角色修改成功'}), 200


# ---------- 管理员：删除用户 ----------
@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@token_required(required_roles=['admin'])
def delete_user(user_id):
    if user_id == g.user_id:
        return jsonify({'error': '不能删除自己'}), 403
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    return jsonify({'message': '用户已删除'}), 200