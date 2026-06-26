import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 设置Seaborn的主题风格
sns.set(style="whitegrid")

# 设置Matplotlib中文字体
# 这里以SimHei为例，如果系统中没有SimHei，可以更换为其他中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 指定默认字体
plt.rcParams['axes.unicode_minus'] = False    # 解决负号 '-' 显示为方块的问题

# 读取CSV文件
# 假设CSV文件名为 'dga_data.csv'，如果文件名不同，请相应修改
df = pd.read_csv('./artifacts/multi/dataset.csv')

# 确认列名是否为 'Domain' 和 'Botnet_Family'
# 如果列名不同，请修改以下代码中的列名
if 'Botnet_Family' not in df.columns:
    raise ValueError("CSV文件中没有 'Botnet_Family' 列。请检查列名是否正确。")

# 统计每种Family的DGA域名数量
family_counts = df['Botnet_Family'].value_counts().reset_index()
family_counts.columns = ['Family', 'Count']

# 按数量排序
family_counts = family_counts.sort_values(by='Count', ascending=True)  # 为了在条形图中从下到上排序

# 设置绘图的大小
plt.figure(figsize=(10, max(6, len(family_counts) * 0.3)))  # 动态调整高度以适应家庭数量

# 创建条形图
sns.barplot(x='Count', y='Family', data=family_counts, palette='viridis')

# 添加标题和标签
plt.title('每种Family的DGA域名数量统计', fontsize=16)
plt.xlabel('数量', fontsize=14)
plt.ylabel('Family', fontsize=14)

# 显示数值标签
for index, value in enumerate(family_counts['Count']):
    plt.text(value, index, str(value), va='center')

# 调整布局以防止标签被截断
plt.tight_layout()

# 显示图表
plt.show()
