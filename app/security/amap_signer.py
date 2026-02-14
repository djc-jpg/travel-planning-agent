"""高德 API 数字签名器

高德 Web Service API 支持数字签名验证机制：
  1. 将所有请求参数按 key 排序拼接
  2. 末尾追加 Secret
  3. 对整个字符串做 MD5 得到 sig 参数

环境变量：
  AMAP_API_KEY    — 高德 API Key（必填）
  AMAP_SECRET     — 高德数字签名密钥（可选，配置后自动启用签名）

参考文档：https://lbs.amap.com/api/webservice/guide/api/direction-walking
"""

from __future__ import annotations

import hashlib

from app.security.key_manager import get_key_manager


def compute_amap_sig(params: dict[str, str], secret: str) -> str:
    """
    按高德签名规则计算 sig。

    算法：
      1. 按参数 key 的 ASCII 升序排序
      2. 拼接为 key1=value1&key2=value2&... 格式
      3. 末尾追加 Secret
      4. 对整个字符串做 MD5
    """
    sorted_items = sorted(params.items(), key=lambda x: x[0])
    raw = "&".join(f"{k}={v}" for k, v in sorted_items)
    raw += secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def sign_amap_params(params: dict[str, str]) -> dict[str, str]:
    """
    为高德 API 请求参数添加数字签名。

    - 自动注入 key 参数
    - 如果配置了 AMAP_SECRET，自动计算并添加 sig 参数
    - 如果未配置 Secret，仅注入 key（保持向后兼容）

    Returns:
        签名后的参数字典（新 dict，不修改原始）
    """
    km = get_key_manager()
    api_key = km.get_amap_key(required=True)
    secret = km.get_amap_secret()

    signed = dict(params)
    signed["key"] = api_key

    if secret:
        sig = compute_amap_sig(signed, secret)
        signed["sig"] = sig

    return signed


def is_signing_enabled() -> bool:
    """检查是否已启用数字签名"""
    km = get_key_manager()
    return km.get_amap_secret() is not None
