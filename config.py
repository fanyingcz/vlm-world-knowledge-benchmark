import os
from openai import OpenAI

# ==================== 配置 ====================
MODEL_CONFIGS = {
    "1": {
        "name": "通义千问 (Qwen)",
        "client_type": "openai",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-vl-max",
        "api_key": None,
    },
    "2": {
        "name": "Google Gemini",
        "client_type": "openai",
        "api_key_env": "GRSAI_API_KEY",
        "base_url": "https://grsai.dakka.com.cn/v1",
        "model_name": "gemini-3.1-pro",
        "api_key": None,
    },
    "3": {
        "name": "火山引擎 (Doubao)",
        "client_type": "openai",
        "api_key_env": "ARK_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model_name": "doubao-seed-2-0-lite-260215",
        "api_key": None,
    },
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# Images are not redistributed with this repository (see data/images/README.md).
# Point this at your local copy, or override with the VLM_BENCH_IMAGE_DIR
# environment variable.
IMAGE_DIR = os.getenv("VLM_BENCH_IMAGE_DIR", os.path.join(DATA_DIR, "images"))

JSON_FILE_MAP = {
    "1": {"file": os.path.join(DATA_DIR, "物理.json"),     "image_folder": os.path.join(IMAGE_DIR, "物理")},
    "2": {"file": os.path.join(DATA_DIR, "生物.json"),     "image_folder": os.path.join(IMAGE_DIR, "生物")},
    "3": {"file": os.path.join(DATA_DIR, "化学.json"),     "image_folder": os.path.join(IMAGE_DIR, "化学")},
    "4": {"file": os.path.join(DATA_DIR, "安全常识.json"), "image_folder": os.path.join(IMAGE_DIR, "安全常识")},
}

REQUEST_INTERVAL = 0.5


# ==================== 模型客户端管理 ====================
class ModelClientManager:
    def __init__(self):
        self.clients = {}
        self._init_clients()

    def _init_clients(self):
        for key, config in MODEL_CONFIGS.items():
            if config["client_type"] == "openai":
                api_key = os.getenv(config["api_key_env"])
                if not api_key:
                    print(f"⚠️ 未设置环境变量 {config['api_key_env']}，{config['name']} 不可用")
                    continue
                config["api_key"] = api_key
                client = OpenAI(api_key=api_key, base_url=config["base_url"])
                self.clients[key] = {"client": client, "config": config}
                print(f"✓ 已加载模型: {config['name']}")

    def get_available_models(self):
        return {key: cfg["config"]["name"] for key, cfg in self.clients.items()}

    def get_client(self, model_key):
        if model_key not in self.clients:
            raise ValueError(f"模型 {model_key} 未配置或API密钥缺失")
        return self.clients[model_key]

    def call_model(self, model_key, messages, temperature=0.1):
        client_info = self.get_client(model_key)
        client = client_info["client"]
        config = client_info["config"]
        try:
            response = client.chat.completions.create(
                model=config["model_name"],
                messages=messages,
                temperature=temperature,
            )
            raw_content = response.choices[0].message.content
            # 简单的 think 标签移除（避免循环引用，直接复制函数）
            import re
            return re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
        except Exception as e:
            print(f"调用 {config['name']} 出错: {e}")
            return ""


model_manager = ModelClientManager()


def call_vision_model_with_messages(messages, model_key=None):
    if model_key is None:
        available = model_manager.get_available_models()
        if not available:
            return ""
        model_key = next(iter(available.keys()))
    return model_manager.call_model(model_key, messages)


def call_vision_model(question, image_path, system_prompt, model_key=None):
    # 导入 encode 以避免循环依赖，在函数内导入
    from utils import encode_image_to_base64, build_messages_with_image
    messages = build_messages_with_image(question, image_path, system_prompt)
    return call_vision_model_with_messages(messages, model_key)