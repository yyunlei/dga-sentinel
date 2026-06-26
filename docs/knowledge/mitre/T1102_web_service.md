# T1102 - Web服务

## 技术信息
- **技术ID**: T1102
- **技术名称**: Web Service
- **战术分类**: Command and Control (C2)

## DGA关联性
部分DGA恶意软件利用合法Web服务（如Pastebin、GitHub、Twitter）作为C2通道或DGA种子来源。Torpig家族曾使用Twitter趋势话题作为DGA种子。

## 检测方法
- 监控对Pastebin等粘贴服务的异常访问
- 检测社交媒体API的非正常调用
- 分析从Web服务下载的加密/编码内容
- 关联DGA活动与Web服务访问时间

## 示例指标
- 恶意进程访问Pastebin/GitHub Raw内容
- 异常的Twitter API调用模式
- 从合法Web服务下载加密配置
- Web服务访问与DGA域名查询时间相关
