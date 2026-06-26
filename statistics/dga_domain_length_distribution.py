import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib

# 设置Seaborn的主题风格
sns.set(style="whitegrid")

# 设置Matplotlib中文字体
# 请根据你的系统中可用的中文字体进行调整
plt.rcParams['font.sans-serif'] = ['SimHei']  # 指定默认字体为SimHei
plt.rcParams['axes.unicode_minus'] = False    # 解决负号 '-' 显示为方块的问题

# 读取CSV文件
# 假设CSV文件名为 'dga_data.csv'，如果文件名不同，请相应修改
df = pd.read_csv('./artifacts/multi/dataset.csv')

# 确认列名是否为 'Domain' 和 'Botnet_Family'
required_columns = ['Domain', 'Botnet_Family']
for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"CSV文件中没有 '{col}' 列。请检查列名是否正确。")

# 过滤出DGA域名（Botnet_Family != 'alexa'）
dga_df = df[df['Botnet_Family'] != 'alexa']

# 统计每种DGA Family的数量
dga_family_counts = dga_df['Botnet_Family'].value_counts().reset_index()
dga_family_counts.columns = ['Family', 'Count']

# 打印DGA Family统计
print("DGA Family统计：")
print(dga_family_counts)

# 按数量排序（从小到大）
dga_family_counts_sorted = dga_family_counts.sort_values(by='Count', ascending=True)

# 设置绘图的大小，动态调整高度以适应Family数量
plt.figure(figsize=(10, max(6, len(dga_family_counts_sorted) * 0.3)))

# 创建水平条形图
sns.barplot(x='Count', y='Family', data=dga_family_counts_sorted, palette='viridis')

# 添加标题和标签
plt.title('每种DGA Family的域名数量统计', fontsize=16)
plt.xlabel('数量', fontsize=14)
plt.ylabel('Family', fontsize=14)

# 在条形上显示数值
for index, value in enumerate(dga_family_counts_sorted['Count']):
    plt.text(value, index, str(value), va='center')

# 调整布局以防止标签被截断
plt.tight_layout()

# 显示图表
plt.show()

# ---------------------------
# 分析并可视化DGA域名的长度分布
# ---------------------------

# 计算域名长度
dga_df['Length'] = dga_df['Domain'].apply(lambda x: len(str(x).strip()))

# 绘制长度分布的直方图
plt.figure(figsize=(12, 8))
sns.histplot(data=dga_df, x='Length', kde=False, color='red', bins=30, alpha=0.7)

# 添加标题和标签
plt.title('DGA域名长度分布', fontsize=16)
plt.xlabel('域名长度', fontsize=14)
plt.ylabel('数量', fontsize=14)

# 调整布局
plt.tight_layout()

# 显示图表
plt.show()

# ---------------------------
# 可选：绘制DGA域名的核密度估计图（KDE）
# ---------------------------

plt.figure(figsize=(12, 8))
sns.kdeplot(data=dga_df, x='Length', shade=True, color='red', label='DGA域名')

plt.title('DGA域名长度分布 (KDE)', fontsize=16)
plt.xlabel('域名长度', fontsize=14)
plt.ylabel('密度', fontsize=14)
plt.legend(title='类别')

plt.tight_layout()
plt.show()
