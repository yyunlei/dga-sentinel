import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ---------------------------
# 1. 设置与数据读取
# ---------------------------

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

# ---------------------------
# 2. 过滤DGA域名并计算长度
# ---------------------------

# 过滤出DGA域名（Botnet_Family != 'alexa'）
dga_df = df[df['Botnet_Family'] != 'alexa'].copy()

# 计算域名长度
dga_df['Length'] = dga_df['Domain'].apply(lambda x: len(str(x).strip()))

# ---------------------------
# 3. 选择展示的DGA家族（可选）
# ---------------------------

# 如果DGA家族数量过多，可以选择展示数量最多的前N个家族
# 这里以展示数量最多的前20个家族为例，若家族数量较少，可适当调整
top_n = 20
dga_family_counts_sorted = dga_df['Botnet_Family'].value_counts().sort_values(ascending=False)
top_dga_families = dga_family_counts_sorted.head(top_n).index
dga_top_df = dga_df[dga_df['Botnet_Family'].isin(top_dga_families)]

# ---------------------------
# 4. 生成箱型图
# ---------------------------

plt.figure(figsize=(max(12, top_n * 0.6), 8))  # 动态调整宽度以适应Family数量

# 创建箱型图
sns.boxplot(x='Length', y='Botnet_Family', data=dga_top_df, palette='Set3')

# 添加标题和标签
plt.title('不同DGA家族域名长度分布箱型图', fontsize=16)
plt.xlabel('域名长度', fontsize=14)
plt.ylabel('DGA Family', fontsize=14)

# 旋转Y轴标签（Family）如果需要的话（根据具体显示情况调整）
# plt.yticks(rotation=45, ha='right')

# 调整布局以防止标签被截断
plt.tight_layout()

# 显示图表
plt.show()
