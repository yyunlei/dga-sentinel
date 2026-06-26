# T1071 - 应用层协议 (Application Layer Protocol)

## ATT&CK 映射
- **战术**: 命令与控制 (Command and Control)
- **技术 ID**: T1071
- **子技术**: T1071.004 DNS

## 与 DGA 的关联
DGA 恶意软件通过 DNS 协议（应用层）与 C2 服务器通信。攻击者利用 DNS 查询作为隐蔽信道，因为大多数网络环境允许 DNS 流量出站。

## 检测策略
- 监控异常 DNS 查询频率和模式
- 检测 DNS 查询中的高熵域名
- 分析 DNS TXT 记录中的可疑编码数据
- 部署 DNS 深度包检测（DPI）识别隧道行为

## 响应措施
- 配置 DNS 防火墙拦截已知恶意域名
- 强制所有 DNS 流量经过企业 DNS 服务器
- 启用 DNS 日志记录并接入 SIEM 平台
- 阻断非标准端口的 DNS 通信
