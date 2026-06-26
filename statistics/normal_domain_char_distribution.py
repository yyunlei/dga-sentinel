import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import matplotlib

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
# 2. 过滤正常域名并统计字符频率
# ---------------------------

# 过滤出正常域名（Botnet_Family == 'alexa'）
normal_df = df[df['Botnet_Family'] == 'alexa'].copy()

# 确保 'Domain' 列没有缺失值
normal_df = normal_df.dropna(subset=['Domain'])

# 合并所有域名为一个字符串，并转换为小写以统一字符
all_domains = ''.join(normal_df['Domain'].astype(str).str.lower().tolist())

# 统计每个字符的频率
char_counts = Counter(all_domains)

# 仅保留字母字符（a-z）
import string
filtered_char_counts = {char: count for char, count in char_counts.items() if char in string.ascii_lowercase}

# 将统计结果转换为DataFrame
char_df = pd.DataFrame(filtered_char_counts.items(), columns=['Character', 'Count'])

# 按照字符排序（a-z）
char_df = char_df.sort_values(by='Character')

# ---------------------------
# 3. 可视化字符分布
# ---------------------------

plt.figure(figsize=(14, 8))

# 创建柱状图
sns.barplot(x='Character', y='Count', data=char_df, palette='viridis')

# 添加标题和标签
plt.title('正常域名（alexa）字符分布', fontsize=16)
plt.xlabel('字符', fontsize=14)
plt.ylabel('字符出现次数', fontsize=14)

# 在柱子上显示数值
for index, row in char_df.iterrows():
    plt.text(row['Character'], row['Count'], str(row['Count']), color='black', ha="center", va="bottom")

# 调整布局以防止标签被截断
plt.tight_layout()

# 显示图表
plt.show()
