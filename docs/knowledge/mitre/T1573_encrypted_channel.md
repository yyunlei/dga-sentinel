# T1573 - 加密信道 (Encrypted Channel)

## ATT&CK 映射
- **战术**: 命令与控制 (Command and Control)
- **技术 ID**: T1573
- **子技术**: T1573.001 对称加密, T1573.002 非对称加密

## 与 DGA 的关联
部分 DGA 恶意软件在通过域名解析建立 C2 连接后，使用加密信道传输指令和窃取数据。DNS over HTTPS (DoH) 和 DNS over TLS (DoT) 也被滥用来隐藏 DGA 查询。

## 检测策略
- 监控异常的 DoH/DoT 流量
- 检测与已知 DoH 提供商的非浏览器连接
- 分析 TLS 握手中的 JA3/JA3S 指纹
- 识别加密流量中的异常数据量和频率模式

## 响应措施
- 在企业网络中限制或代理 DoH/DoT 流量
- 部署 TLS 检测设备进行中间人解密分析
- 维护 JA3 指纹黑名单用于恶意软件识别
- 结合 NetFlow 数据分析加密流量行为特征
