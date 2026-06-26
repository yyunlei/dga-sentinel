# 导入必要的库
import numpy as np  # 用于数值计算
import pandas as pd  # 用于数据处理
import matplotlib.pyplot as plt  # 用于绘制图表
import re  # 用于正则表达式
import seaborn as sns  # 用于高级数据可视化
from sklearn.feature_extraction.text import TfidfVectorizer  # 用于TF-IDF特征提取
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold  # 用于数据集划分与交叉验证
from sklearn.metrics import accuracy_score, f1_score, roc_curve, auc, roc_auc_score  # 用于评估模型性能
from sklearn.preprocessing import StandardScaler  # 用于数据标准化
from sklearn.linear_model import LogisticRegression  # 用于逻辑回归模型
from sklearn.neighbors import KNeighborsClassifier  # 用于KNN分类器
from sklearn.ensemble import RandomForestClassifier  # 用于随机森林分类器
import xgboost as xgb  # 用于XGBoost模型
# import lightgbm as lgb  # 用于LightGBM模型
from scipy.stats import skew, kurtosis  # 用于计算偏度与峰度
import joblib  # 用于模型保存与加载
import gc  # 用于垃圾回收，优化内存使用

# 读取数据文件
FILE = 'artifacts/test_dataset.csv'  # 数据文件路径
df = pd.read_csv(FILE)  # 读取CSV文件

# 打乱数据顺序
df = df.sample(frac=1, random_state=42).reset_index(drop=True)  # 打乱数据，确保数据顺序随机

# 仅保留域名和目标标签
df = df[['Domain', 'Target']]  # 只保留 'Domain' 和 'Target' 列

# 定义函数：提取域名的特征
def count_features(domain):
    L = len(domain)  # 域名长度
    consonant_count = sum(1 for char in domain if char in 'bcdfghjklmnpqrstvwxyz')  # 辅音字母个数
    Rc = consonant_count / L if L > 0 else 0  # 辅音比例
    letter_count = sum(1 for char in domain if char.isalpha())  # 字母个数
    Rl = letter_count / L if L > 0 else 0  # 字母比例
    number_count = sum(1 for char in domain if char.isdigit())  # 数字个数
    Rn = number_count / L if L > 0 else 0  # 数字比例
    vowel_count = sum(1 for char in domain if char in 'aeiou')  # 元音字母个数
    Rv = vowel_count / L if L > 0 else 0  # 元音比例
    symbolic_count = sum(1 for char in domain if not char.isalnum())  # 符号字符个数
    Rs = symbolic_count / L if L > 0 else 0  # 符号比例
    return L, Rc, Rv, Rn, Rl, Rs  # 返回各个特征

# 定义函数：计算每个域名的多个特征
def calculate_features(df):
    features = []  # 存储所有域名的特征
    for domain in df['Domain']:  # 遍历每个域名
        parts = domain.split('.')  # 分割域名
        subdomain = '.'.join(parts[:-2]) if len(parts) >= 3 else ''  # 子域名部分（如果有）
        sld = parts[-2]  # 二级域名
        tld = parts[-1]  # 顶级域名
        N = 3 if subdomain else 2  # 如果有子域名，N为3，否则为2
        consonants = re.findall(r'[^aeiou\d\s\W]+', domain)  # 查找域名中的辅音
        LCc = max(len(consonant) for consonant in consonants) if consonants else 0  # 辅音最大长度
        numbers = re.findall(r'\d+', domain)  # 查找域名中的数字
        LCn = max(len(number) for number in numbers) if numbers else 0  # 数字最大长度
        vowels = re.findall(r'[aeiou]+', domain)  # 查找域名中的元音
        LCv = max(len(vowel) for vowel in vowels) if vowels else 0  # 元音最大长度
        L_tld, Rc_tld, Rv_tld, Rn_tld, Rl_tld, Rs_tld = count_features(tld)  # 计算顶级域名的特征
        L_sld, Rc_sld, Rv_sld, Rn_sld, Rl_sld, Rs_sld = count_features(sld)  # 计算二级域名的特征
        L_sub, Rc_sub, Rv_sub, Rn_sub, Rl_sub, Rs_sub = count_features(subdomain) if subdomain else (0, 0, 0, 0, 0, 0)  # 计算子域名的特征（如果有）
        features.append([N, LCc, LCv, LCn, L_tld, Rc_tld, Rv_tld, Rn_tld, Rl_tld, Rs_tld,
                         L_sld, Rc_sld, Rv_sld, Rn_sld, Rl_sld, Rs_sld, L_sub, Rc_sub, Rv_sub, Rn_sub, Rl_sub, Rs_sub])  # 添加到特征列表
    feature_columns = ['N', 'LCc', 'LCv', 'LCn', 'L_tld', 'Rc_tld', 'Rv_tld', 'Rn_tld', 'Rl_tld', 'Rs_tld',
                       'L_sld', 'Rc_sld', 'Rv_sld', 'Rn_sld', 'Rl_sld', 'Rs_sld',
                       'L_sub', 'Rc_sub', 'Rv_sub', 'Rn_sub', 'Rl_sub', 'Rs_sub']  # 特征列名
    feature_df = pd.DataFrame(features, columns=feature_columns)  # 将特征列表转换为DataFrame
    return pd.concat([df.reset_index(drop=True), feature_df], axis=1)  # 将特征与原数据合并

# 计算每个域名的自定义特征
print("计算自定义特征...")
df_custom_features = calculate_features(df)  # 调用计算特征的函数
print("自定义特征计算完成。")

# 创建n-gram特征提取器，并限制最大特征数量
print("创建n-gram向量器...")
unigrams = TfidfVectorizer(analyzer='char', ngram_range=(1, 1), max_features=1000)  # 单字n-gram提取器
bigrams = TfidfVectorizer(analyzer='char', ngram_range=(2, 2), max_features=1000)  # 双字n-gram提取器
trigrams = TfidfVectorizer(analyzer='char', ngram_range=(3, 3), max_features=1000)  # 三字n-gram提取器

# 仅在所有数据上拟合向量器
print("拟合n-gram向量器...")
unigrams.fit(df['Domain'])  # 拟合单字特征
bigrams.fit(df['Domain'])  # 拟合双字特征
trigrams.fit(df['Domain'])  # 拟合三字特征
print("n-gram向量器拟合完成。")

# 定义n-gram统计特征提取函数
def ngrams_features_per_sample(matrix, prefix):
    ngram_frequencies = matrix  # 获取n-gram矩阵
    features_list = []  # 特征列表
    for sample_frequencies in ngram_frequencies:  # 遍历每个样本的特征
        features = {}  # 特征字典
        if sample_frequencies.nnz > 0:  # 如果有n-gram特征
            data = sample_frequencies.data  # 获取非零特征数据
            features[f'{prefix}-DIST'] = sample_frequencies.nnz  # 特征的非零计数
            features[f'{prefix}-MEAN'] = data.mean()  # 平均值
            features[f'{prefix}-QMEAN'] = np.sqrt(np.mean(data ** 2))  # 均方根值
            features[f'{prefix}-SUMSQ'] = np.sum(data ** 2)  # 求平方和
            features[f'{prefix}-VAR'] = np.var(data)  # 方差
            features[f'{prefix}-PVAR'] = np.var(data, ddof=0)  # 无偏方差
            features[f'{prefix}-STD'] = np.std(data)  # 标准差
            features[f'{prefix}-PSTD'] = np.std(data, ddof=0)  # 无偏标准差
            features[f'{prefix}-SKE'] = skew(data) if len(data) > 2 else 0  # 偏度
            features[f'{prefix}-KUR'] = kurtosis(data) if len(data) > 3 else 0  # 峰度
        else:
            for metric in ['DIST', 'MEAN', 'QMEAN', 'SUMSQ', 'VAR', 'PVAR', 'STD', 'PSTD', 'SKE', 'KUR']:
                features[f'{prefix}-{metric}'] = 0  # 如果没有特征，则赋值为0
        features_list.append(features)  # 将特征添加到列表
    return pd.DataFrame(features_list)  # 返回特征DataFrame

# 定义批处理函数
def process_batch(domains, unigrams, bigrams, trigrams):
    unigrams_matrix = unigrams.transform(domains)  # 转换单字特征矩阵
    bigrams_matrix = bigrams.transform(domains)  # 转换双字特征矩阵
    trigrams_matrix = trigrams.transform(domains)  # 转换三字特征矩阵
    
    unigrams_features = ngrams_features_per_sample(unigrams_matrix, prefix='UNI')  # 提取单字特征
    bigrams_features = ngrams_features_per_sample(bigrams_matrix, prefix='BI')  # 提取双字特征
    trigrams_features = ngrams_features_per_sample(trigrams_matrix, prefix='TRI')  # 提取三字特征
    
    ngram_features = pd.concat([unigrams_features, bigrams_features, trigrams_features], axis=1)  # 合并特征
    return ngram_features  # 返回n-gram特征

# 分批处理n-gram特征
print("开始分批提取n-gram特征...")
batch_size = 10000  # 设置批次大小
num_batches = int(np.ceil(len(df) / batch_size))  # 计算批次数
df_ngrams_features = []  # 存储所有n-gram特征

for i in range(num_batches):
    start_idx = i * batch_size  # 批次开始索引
    end_idx = min((i + 1) * batch_size, len(df))  # 批次结束索引
    batch_domains = df['Domain'].iloc[start_idx:end_idx]  # 获取当前批次的域名
    batch_features = process_batch(batch_domains, unigrams, bigrams, trigrams)  # 提取特征
    df_ngrams_features.append(batch_features)  # 添加到特征列表
    print(f"已处理批次 {i+1}/{num_batches}")  # 输出当前进度
    
    # 释放内存
    del batch_domains, batch_features
    gc.collect()

# 合并所有批次的n-gram特征
df_ngrams_features = pd.concat(df_ngrams_features, axis=0).reset_index(drop=True)  # 合并n-gram特征
print("n-gram特征提取完成。")

# 释放内存
del df
gc.collect()

# 拼接所有特征
print("拼接自定义特征和n-gram特征...")
df_final = pd.concat([df_custom_features, df_ngrams_features], axis=1)  # 拼接特征
print("特征拼接完成。")

# 准备训练数据
X = df_final.drop(['Domain', 'Target'], axis=1)  # 特征数据
y = df_final['Target']  # 标签数据

# 释放内存
del df_custom_features, df_ngrams_features
gc.collect()

# 划分训练集和测试集
print("划分训练集和测试集...")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y  # 按照比例划分训练集和测试集
)
print("数据集划分完成。")

# 释放内存
del X, y
gc.collect()

# 数据标准化
print("标准化数据...")
scaler = StandardScaler()  # 初始化标准化器
X_train = scaler.fit_transform(X_train)  # 拟合并转换训练集数据
X_test = scaler.transform(X_test)  # 转换测试集数据
print("数据标准化完成。")

# 定义要训练的模型
models = {
    'XGBoost': xgb.XGBClassifier(  # 定义XGBoost模型
        eval_metric='mlogloss',
        use_label_encoder=False,
        random_state=42,
        colsample_bytree=0.8,
        learning_rate=0.3,
        max_depth=10,
        n_estimators=150,
        subsample=1.0,
        n_jobs=-1
    )
}

# 设置交叉验证次数
k = 5  # 5折交叉验证
results = {'Accuracy': {}, 'F1 Score': {}}  # 存储评估指标
roc_curves = {}  # 存储ROC曲线数据

# 对每个模型进行训练、评估和ROC曲线绘制
print("开始训练和评估模型...")
for model_name, model in models.items():  # 遍历所有模型
    print(f"训练模型: {model_name}")
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)  # 初始化交叉验证
    accuracy_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='accuracy')  # 计算准确率
    f1_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='f1')  # 计算F1分数
    
    results['Accuracy'][model_name] = accuracy_scores.mean()  # 平均准确率
    results['F1 Score'][model_name] = f1_scores.mean()  # 平均F1分数
    
    model.fit(X_train, y_train)  # 训练模型
    y_pred = model.predict(X_test)  # 预测测试集标签
    
    # 计算ROC曲线和AUC值
    if hasattr(model, "predict_proba"):
        y_score = model.predict_proba(X_test)[:, 1]  # 预测概率
    else:
        y_score = model.decision_function(X_test)  # 获取决策函数的输出
    
    fpr, tpr, _ = roc_curve(y_test, y_score)  # 计算假阳性率与真正性率
    roc_auc = auc(fpr, tpr)  # 计算AUC值
    roc_curves[model_name] = (fpr, tpr, roc_auc)  # 存储ROC曲线数据
    
    print(f"{model_name} - Accuracy: {accuracy_scores.mean():.4f} | F1 Score: {f1_scores.mean():.4f} | ROC AUC: {roc_auc:.4f}")  # 输出评估结果

print("模型训练和评估完成。")

# 绘制ROC曲线
print("绘制ROC曲线...")
plt.figure(figsize=(10, 8))  # 创建画布

for model_name, (fpr, tpr, roc_auc) in roc_curves.items():  # 遍历每个模型的ROC数据
    plt.plot(fpr, tpr, label=f'{model_name} (AUC = {roc_auc:.4f})')  # 绘制ROC曲线

# 绘制随机模型的对比线
plt.plot([0, 1], [0, 1], 'k--', label='Random')  # 绘制随机模型的对比线
plt.xlabel('False Positive Rate')  # X轴标签
plt.ylabel('True Positive Rate')  # Y轴标签
plt.title('ROC Curves of Models')  # 标题
plt.legend(loc='best')  # 图例位置
plt.grid(True)  # 网格
plt.show()  # 显示图表
print("ROC曲线绘制完成。")

# 打印总结结果
print("\n模型评估结果:")
results_df = pd.DataFrame(results).T  # 将结果转换为DataFrame
print(results_df)

# 保存模型和向量器（可选）
# print("保存模型和向量器...")
# joblib.dump(unigrams, 'unigram_vectorizer.pkl')
# joblib.dump(bigrams, 'bigram_vectorizer.pkl')
# joblib.dump(trigrams, 'trigram_vectorizer.pkl')
# joblib.dump(scaler, 'scaler.pkl')

# 仅保存XGBoost和LightGBM模型作为示例，您可以根据需要保存其他模型
# joblib.dump(models['XGBoost'], 'xgb_model.pkl')
# joblib.dump(models['LightGBM'], 'lgbm_model.pkl')
# print("模型和向量器保存完成。")
