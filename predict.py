import joblib  # 导入joblib库，用于加载已训练的模型和工具
import numpy as np  # 导入numpy库，用于数组处理和数值计算
import pandas as pd  # 导入pandas库，用于数据框处理
import re  # 导入正则表达式库，用于字符串匹配和处理
from tensorflow.keras.preprocessing.sequence import pad_sequences  # 导入Keras中的pad_sequences函数，用于文本数据预处理
from scipy.stats import skew, kurtosis  # 导入scipy库中的skew和kurtosis，用于统计分析
import xgboost  # 导入XGBoost库（虽然代码中没有直接使用）
from tensorflow.keras.models import load_model
# 定义二分类预测类
class bin_predict:
    def __init__(self, input_domain):
        self.input_domain = input_domain  # 接收输入的域名
        # 加载训练好的二分类模型和特征提取工具
        self.binary_model = joblib.load("artifacts/binary/binary_classification_model.pkl")
        self.unigrams = joblib.load("artifacts/binary/unigram_vectorizer.pkl")
        self.bigrams = joblib.load("artifacts/binary/bigram_vectorizer.pkl")
        self.trigrams = joblib.load("artifacts/binary/trigram_vectorizer.pkl")
        self.scaler = joblib.load("artifacts/binary/scaler.pkl")

    # 计算域名的特征
    def count_features(self, domain):
        L = len(domain)  # 域名的长度
        consonant_count = sum(1 for char in domain if char in 'bcdfghjklmnpqrstvwxyz')  # 辅音字母计数
        Rc = consonant_count / len(domain) if len(domain) > 0 else 0  # 辅音字母比例

        letter_count = sum(1 for char in domain if char.isalpha())  # 字母字符计数
        Rl = letter_count / len(domain) if len(domain) > 0 else 0  # 字母比例

        number_count = sum(1 for char in domain if char.isdigit())  # 数字字符计数
        Rn = number_count / len(domain) if len(domain) > 0 else 0  # 数字比例

        vowel_count = sum(1 for char in domain if char in 'aeiou')  # 元音字母计数
        Rv = vowel_count / len(domain) if len(domain) > 0 else 0  # 元音字母比例

        symbolic_count = sum(1 for char in domain if not char.isalnum())  # 非字母数字字符计数
        Rs = symbolic_count / len(domain) if len(domain) > 0 else 0  # 特殊字符比例

        return L, Rc, Rv, Rn, Rl, Rs  # 返回计算得到的各项特征

    # 计算自定义特征（如最长子串的长度等）
    def calc_custom_features(self):
        features = []  # 用于存储特征的列表
        parts = self.input_domain.split('.')  # 将域名按“.”分割成各个部分
        subdomain = '.'.join(parts[:-2]) if len(parts) >= 3 else ''  # 获取子域名（如果有的话）
        sld = parts[-2]  # 获取二级域名（SLD）
        tld = parts[-1]  # 获取顶级域名（TLD）

        N = 3 if subdomain else 2  # 如果有子域名，则N=3，否则N=2

        # 正则表达式提取出域名中的辅音字母、数字和元音字母
        consonants = re.findall(r'[^aeiou\d\s\W]+', self.input_domain)
        LCc = max(len(consonant) for consonant in consonants) if consonants else 0  # 获取最长辅音子串的长度
        numbers = re.findall(r'\d+', self.input_domain)
        LCn = max(len(number) for number in numbers) if numbers else 0  # 获取最长数字子串的长度
        vowels = re.findall(r'[aeiou]+', self.input_domain)
        LCv = max(len(vowel) for vowel in vowels) if vowels else 0  # 获取最长元音子串的长度

        # 计算TLD、SLD和子域名的各类特征
        L_tld, Rc_tld, Rv_tld, Rn_tld, Rl_tld, Rs_tld = self.count_features(tld)
        L_sld, Rc_sld, Rv_sld, Rn_sld, Rl_sld, Rs_sld = self.count_features(sld)
        L_sub, Rc_sub, Rv_sub, Rn_sub, Rl_sub, Rs_sub = self.count_features(subdomain) if subdomain else (0, 0, 0, 0, 0, 0)

        # 将各类特征按顺序添加到特征列表
        features.append([N, LCc, LCv, LCn, 
                        L_tld, Rc_tld, Rv_tld, Rn_tld, Rl_tld, Rs_tld,
                        L_sld, Rc_sld, Rv_sld, Rn_sld, Rl_sld, Rs_sld,
                        L_sub, Rc_sub, Rv_sub, Rn_sub, Rl_sub, Rs_sub])
        
        # 定义特征列的名称
        feature_columns = ['N', 'LCc', 'LCv', 'LCn',
                    'L_tld', 'Rc_tld', 'Rv_tld', 'Rn_tld', 'Rl_tld','Rs_tld',
                    'L_sld', 'Rc_sld', 'Rv_sld', 'Rn_sld', 'Rl_sld','Rs_sld',
                    'L_sub', 'Rc_sub', 'Rv_sub', 'Rn_sub', 'Rl_sub', 'Rs_sub']
        
        # 返回计算得到的特征数据框
        return pd.DataFrame(features, columns=feature_columns)
    
    # 计算n-grams特征
    def ngrams_features_per_sample(self, matrix, prefix):
        # 将稀疏矩阵转为密集矩阵
        ngram_frequencies = matrix.toarray()

        features_list = []  # 存储特征的列表

        # 遍历每个样本的n-grams频率
        for sample_frequencies in ngram_frequencies:
            features = {}

            # 计算n-grams的统计特征（均值、方差、标准差、偏度、峰度）
            if np.count_nonzero(sample_frequencies) > 0:  # 如果有n-gram
                features[f'{prefix}-MEAN'] = np.mean(sample_frequencies)  # 均值
                features[f'{prefix}-VAR'] = np.var(sample_frequencies)  # 方差
                features[f'{prefix}-PVAR'] = np.var(sample_frequencies, ddof=0)  # 总体方差
                features[f'{prefix}-STD'] = np.std(sample_frequencies)  # 标准差
                features[f'{prefix}-PSTD'] = np.std(sample_frequencies, ddof=0)  # 总体标准差
                features[f'{prefix}-SKE'] = skew(sample_frequencies)  # 偏度
                features[f'{prefix}-KUR'] = kurtosis(sample_frequencies)  # 峰度
            else:
                # 如果没有n-grams，设置特征为0
                features[f'{prefix}-MEAN'] = 0
                features[f'{prefix}-VAR'] = 0
                features[f'{prefix}-PVAR'] = 0
                features[f'{prefix}-STD'] = 0
                features[f'{prefix}-PSTD'] = 0
                features[f'{prefix}-SKE'] = 0  # 偏度为0
                features[f'{prefix}-KUR'] = 0  # 峰度为0

            # 将特征添加到特征列表中
            features_list.append(features)

        # 将特征字典列表转换为DataFrame
        return pd.DataFrame(features_list)

    # 计算所有的n-grams特征（unigrams, bigrams, trigrams）
    def calc_ngrams(self):
        # 对输入的域名应用unigram, bigram, trigram向量化
        unigrams_matrix = self.unigrams.transform([self.input_domain])
        bigrams_matrix = self.bigrams.transform([self.input_domain])
        trigrams_matrix = self.trigrams.transform([self.input_domain])

        # 提取n-grams特征
        unigrams_features_df = self.ngrams_features_per_sample(unigrams_matrix, prefix='UNI')
        bigrams_features_df = self.ngrams_features_per_sample(bigrams_matrix, prefix='BI')
        trigrams_features_df = self.ngrams_features_per_sample(trigrams_matrix, prefix='TRI')

        # 合并unigrams、bigrams和trigrams的特征
        df_ngrams_features = pd.concat([unigrams_features_df, bigrams_features_df, trigrams_features_df], axis=1)

        # 返回所有的n-grams特征
        return df_ngrams_features
    
    # 对所有特征进行缩放
    def scaling(self):
        X = pd.concat([self.calc_custom_features(), self.calc_ngrams()], axis=1)  # 合并自定义特征和n-grams特征
        return self.scaler.transform(X)  # 使用预训练的缩放器进行数据缩放
    
    # 进行二分类预测
    def predict(self):
        label = self.binary_model.predict(self.scaling())  # 使用缩放后的特征进行预测
        return label[0]  # 返回预测结果

# 定义多分类预测类
class multi_predict:
    def __init__(self, input_domain):
        self.input_domain = input_domain  # 接收输入的域名
        self.max_sequence_length = 50  # 设置最大序列长度
        # 加载多分类模型和工具
        self.multiclass_model = load_model("artifacts/multi/multiclass_classification_model.h5")
        self.tokenizer = joblib.load("artifacts/multi/tokenizer.pkl")
        self.encoder = joblib.load("artifacts/multi/encoder_multi.pkl")

    # 预处理域名文本
    def preprocess(self):
        sequence = self.tokenizer.texts_to_sequences([self.input_domain])  # 将域名转为整数序列
        padded_sequence = pad_sequences(sequence, maxlen=self.max_sequence_length, padding='post')  # 填充序列到固定长度
        return padded_sequence  # 返回处理后的序列

    # 进行多分类预测
    def predict(self):
        processed_input = self.preprocess()  # 预处理输入

        # 获取模型预测结果
        prediction = self.multiclass_model.predict(processed_input)

        # 获取前3个最可能的预测类别和对应的概率
        top_3_indices = np.argsort(prediction[0])[-3:][::-1]  # 获取前3个类别的索引
        top_3_probs = prediction[0][top_3_indices]  # 获取前3个类别的概率
        top_3_classes = self.encoder.inverse_transform(top_3_indices)  # 获取对应类别的标签

        # 将类别和概率结合成字典列表
        top_3_predictions = [{"class": top_3_classes[i], "probability": float(top_3_probs[i])} for i in range(3)]

        return top_3_predictions  # 返回前3个预测结果
