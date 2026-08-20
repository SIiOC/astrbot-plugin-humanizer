# -*- coding: utf-8 -*-
"""style_core — 人类对话风格插件核心逻辑包。

本包不依赖 astrbot 框架，全部为纯函数/纯数据结构，便于单元测试。
入口编排见各子模块：
- profiles:        风格档案的加载、校验、查询
- inject:          档案 + 检索示例 → system_prompt 指令段渲染
- corpus:          多格式语料解析、去重、采样、语料池管理
- retrieve:        检索结果的格式化与兜底
- extract_prompt:  LLM 提炼/融合风格档案的提示词构造
"""
