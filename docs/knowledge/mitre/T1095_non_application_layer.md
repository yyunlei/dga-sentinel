# T1095 - 非应用层协议

## 技术信息
- **技术ID**: T1095
- **技术名称**: Non-Application Layer Protocol
- **战术分类**: Command and Control (C2)

## DGA关联性
部分DGA恶意软件在解析域名后，使用非标准协议（如原始TCP/UDP、ICMP）与C2服务器通信。DNS解析仅用于获取C2 IP地址，实际数据传输使用自定义协议。

## 检测方法
- 监控非标准端口的TCP/UDP连接
- 检测ICMP隧道流量
- 分析网络流量中的自定义协议特征
- 使用DPI（深度包检测）识别异常协议

## 示例指标
- DGA域名解析后的非HTTP/HTTPS连接
- 异常的ICMP数据包大小
- 非标准端口的持续连接
- 自定义协议头部特征
