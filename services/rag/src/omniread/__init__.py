"""Omniread RAG 服务。

分层（M0-01 §2）：api 只做协议转换，application 编排，domain 放模型与事件，
infrastructure 接外部系统，pipelines 放导入 / 分块 / 检索 / 装配 / 回答算法。
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
