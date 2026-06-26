# 导入必要的库
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import PCA

# 读取CSV文件
# FILE = './artifacts/multi/dataset.csv'
FILE = './artifacts/binary/dga_binary_test.csv'
df = pd.read_csv(FILE)

# 确保数据中包含 'Domain', 'Target' 和 'Family' 列
df = df[['Domain', 'Target', 'Botnet_Family']]

# 打乱数据顺序
df = df.sample(frac=1, random_state=42).reset_index(drop=True)

# 创建n-gram向量器
unigrams = TfidfVectorizer(analyzer='char', ngram_range=(1, 1), max_features=1000)
bigrams = TfidfVectorizer(analyzer='char', ngram_range=(2, 2), max_features=1000)
trigrams = TfidfVectorizer(analyzer='char', ngram_range=(3, 3), max_features=1000)

# 拟合n-gram向量器
unigrams.fit(df['Domain'])
bigrams.fit(df['Domain'])
trigrams.fit(df['Domain'])

# 定义函数：提取n-gram特征并将其可视化
def plot_ngrams_pca_by_family(df, unigrams, bigrams, trigrams):
    # 计算n-gram特征矩阵
    unigrams_matrix = unigrams.transform(df['Domain'])
    bigrams_matrix = bigrams.transform(df['Domain'])
    trigrams_matrix = trigrams.transform(df['Domain'])
    
    # 将n-gram矩阵拼接在一起
    ngram_matrix = np.hstack([unigrams_matrix.toarray(), bigrams_matrix.toarray(), trigrams_matrix.toarray()])
    
    # 使用PCA将特征降到二维
    pca = PCA(n_components=2)
    pca_result = pca.fit_transform(ngram_matrix)
    
    # 创建DataFrame以便绘制
    pca_df = pd.DataFrame(data=pca_result, columns=['PCA1', 'PCA2'])
    pca_df['Botnet_Family'] = df['Botnet_Family']  # 使用DGA家族作为颜色区分
    
    # 绘制散点图
    plt.figure(figsize=(12, 8))
    sns.scatterplot(data=pca_df, x='PCA1', y='PCA2', hue='Botnet_Family', palette='Set1', s=100, edgecolor=None, legend='full')
    
    # 设置图标题和轴标签
    plt.title('PCA of n-grams Vectors by DGA Family')
    plt.xlabel('Principal Component 1')
    plt.ylabel('Principal Component 2')
    plt.legend(title='DGA Family', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True)
    plt.show()

# 调用函数并生成可视化
plot_ngrams_pca_by_family(df, unigrams, bigrams, trigrams)
