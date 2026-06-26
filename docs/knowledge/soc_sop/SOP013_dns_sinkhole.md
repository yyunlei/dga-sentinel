# SOP013 - DNS Sinkhole部署

## SOP信息
- **编号**: SOP013
- **标题**: DGA域名DNS Sinkhole部署流程
- **触发条件**: 需要对已知DGA域名进行Sinkhole处理

## 响应步骤
1. 收集需要Sinkhole的DGA域名列表
2. 验证域名列表（排除合法域名）
3. 配置DNS服务器将目标域名解析到Sinkhole IP
4. 部署Sinkhole服务器记录连接请求
5. 验证Sinkhole生效（测试DNS解析）
6. 监控Sinkhole日志识别感染主机
7. 定期更新Sinkhole域名列表

## 升级标准
- Sinkhole日志显示大量感染主机时通知安全主管
- 发现新的DGA变种绕过Sinkhole时更新规则

## 使用工具
- DNS服务器、Sinkhole服务器、日志分析平台
