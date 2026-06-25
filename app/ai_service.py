"""AI模型服务层 - 支持多供应商、自动切换、统一接口"""
import json
import logging
import time
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from .models import AIProvider

logger = logging.getLogger(__name__)

# 支持的供应商类型及其默认配置
PROVIDER_DEFAULTS = {
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "zhipu": {
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-plus",
    },
    "qwen": {
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "moonshot": {
        "api_base": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-128k",
    },
    "ollama": {
        "api_base": "http://localhost:11434/v1",
        "model": "qwen2.5:32b",
    },
    "custom": {
        "api_base": "",
        "model": "",
    },
}

PROVIDER_LABELS = {
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "zhipu": "智谱AI (GLM)",
    "qwen": "通义千问 (Qwen)",
    "moonshot": "月之暗面 (Kimi)",
    "ollama": "Ollama (本地)",
    "custom": "自定义 (OpenAI兼容)",
}


def get_available_providers(db: Session) -> list:
    """获取所有可用的供应商，按优先级排序"""
    providers = (
        db.query(AIProvider)
        .filter(AIProvider.is_active == True)
        .order_by(AIProvider.priority.desc(), AIProvider.id)
        .all()
    )
    return providers


def call_ai_chat(provider: AIProvider, messages: list, max_tokens: int = None, temperature: float = None) -> dict:
    """调用AI模型的chat接口（统一OpenAI兼容格式）

    返回: {"content": str, "model": str, "usage": dict}
    """
    api_base = provider.api_base.rstrip("/")
    url = f"{api_base}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    payload = {
        "model": provider.model_name,
        "messages": messages,
        "max_tokens": max_tokens or provider.max_tokens,
        "temperature": temperature if temperature is not None else provider.temperature,
    }

    timeout = 180.0  # 分析任务可能耗时较长
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    return {
        "content": content,
        "model": data.get("model", provider.model_name),
        "usage": usage,
    }


def analyze_with_failover(db: Session, messages: list, max_tokens: int = None) -> tuple:
    """带自动切换的AI分析调用

    按优先级尝试所有可用供应商，直到成功。
    返回: (AIProvider, response_dict)
    异常: 所有供应商都失败时抛出最后一个异常
    """
    providers = get_available_providers(db)
    if not providers:
        raise RuntimeError("没有配置可用的AI模型供应商，请先在管理页面添加")

    last_error = None
    for provider in providers:
        try:
            logger.info(f"尝试使用 {provider.name} ({provider.model_name}) 进行分析...")
            result = call_ai_chat(provider, messages, max_tokens=max_tokens)

            # 更新供应商状态为健康
            provider.is_healthy = True
            provider.last_error = None
            provider.last_used_at = datetime.now()
            db.commit()

            logger.info(f"使用 {provider.name} 分析成功")
            return provider, result

        except Exception as e:
            last_error = e
            error_msg = str(e)
            logger.warning(f"供应商 {provider.name} 调用失败: {error_msg}")

            # 标记为不健康
            provider.is_healthy = False
            provider.last_error = error_msg[:500]
            db.commit()
            continue

    raise RuntimeError(f"所有AI供应商均调用失败。最后错误: {last_error}")


def test_provider(provider: AIProvider) -> dict:
    """测试供应商连通性

    返回: {"success": bool, "message": str, "model": str}
    """
    try:
        result = call_ai_chat(provider, [
            {"role": "user", "content": "你好，请用一句话回复。"}
        ], max_tokens=100, temperature=0.1)
        return {
            "success": True,
            "message": f"连接成功，模型: {result['model']}",
            "model": result["model"],
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"连接失败: {str(e)[:200]}",
            "model": provider.model_name,
        }
