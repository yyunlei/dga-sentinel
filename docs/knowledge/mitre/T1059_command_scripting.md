# T1059 - 命令和脚本解释器

## 技术信息
- **技术ID**: T1059
- **技术名称**: Command and Scripting Interpreter
- **战术分类**: Execution（执行）

## DGA关联性
DGA恶意软件常通过PowerShell、CMD、Python等脚本解释器执行DGA算法和C2通信。脚本化的DGA实现便于快速修改和更新算法。

## 检测方法
- 监控PowerShell/CMD的异常执行
- 检测脚本中的DGA算法特征
- 分析脚本执行后的DNS查询模式
- 使用AMSI（反恶意软件扫描接口）检测

## 示例指标
- PowerShell执行包含域名生成逻辑的脚本
- CMD执行nslookup查询大量随机域名
- Python脚本中包含日期相关的字符串生成
- 脚本执行与大量NXDomain响应时间相关
