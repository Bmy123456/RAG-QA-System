"""
日志工具：统一日志格式、级别和输出。

用法：
    from backend.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("处理完成")
"""

from __future__ import annotations

import logging
import sys


# 默认格式
_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 已初始化的 logger 缓存，避免重复添加 handler
_initialized: set[str] = set()


def get_logger(name: str, level: int | None = None) -> logging.Logger:
    """获取指定名称的 logger，自动配置 handler 和格式。

    参数:
        name:  logger 名称，通常传 __name__
        level: 日志级别，默认 INFO。可选 DEBUG / WARNING / ERROR / CRITICAL

    返回:
        配置好的 logging.Logger 实例
    """
    logger = logging.getLogger(name)

    if name not in _initialized:
        logger.setLevel(level or logging.INFO)
        logger.propagate = False  # 避免重复输出

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level or logging.INFO)
        handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATE_FORMAT))
        logger.addHandler(handler)

        _initialized.add(name)

    return logger


def set_global_level(level: int) -> None:
    """全局设置所有已注册 logger 的级别。"""
    for name in _initialized:
        logging.getLogger(name).setLevel(level)
