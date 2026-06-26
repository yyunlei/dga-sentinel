# legacy/

旧 FastAPI + Jinja 单体 demo,已被 `src/` 模块化架构取代,仅留作血缘参考(不被运行时引用)。

- `app.py` / `predict.py` — 早期单文件 FastAPI + 预测逻辑(现 `src/ai/scoring` 的前身)
- `static/` `templates/` — 旧 Jinja 模板与静态资源
