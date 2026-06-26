# 导入必要的库
import numpy as np  # 导入numpy库，用于数值计算
import pandas as pd  # 导入pandas库，用于数据处理
import matplotlib.pyplot as plt  # 导入matplotlib库，用于绘图
import seaborn as sns  # 导入seaborn库，用于数据可视化
import re  # 导入正则表达式库

# 导入TensorFlow和Keras相关工具
from tensorflow.keras.preprocessing.text import Tokenizer  # 导入Tokenizer类，用于文本预处理
from tensorflow.keras.preprocessing.sequence import pad_sequences  # 导入pad_sequences，用于将文本序列填充到固定长度
import tensorflow as tf  # 导入TensorFlow库
from tensorflow.keras.utils import to_categorical  # 导入to_categorical，用于将标签转换为分类格式
from tensorflow.keras.models import Model  # 导入Model类，用于构建模型
from tensorflow.keras.layers import (
    Input, Embedding, Conv1D, MaxPooling1D, Dropout, Dense,  # 导入常用的层，如输入层、卷积层、池化层、全连接层等
    Flatten, MultiHeadAttention, LayerNormalization, Add
)
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau  # 导入早停和学习率减少回调函数

# 导入sklearn相关工具
from sklearn.model_selection import train_test_split  # 导入train_test_split，用于数据集划分
from sklearn.preprocessing import LabelEncoder  # 导入LabelEncoder，用于标签编码
from sklearn.utils import class_weight  # 导入class_weight，用于处理类不平衡问题
from sklearn.metrics import classification_report, confusion_matrix  # 导入分类报告和混淆矩阵计算工具
import joblib  # 导入joblib，用于模型和对象的保存

# 读取数据文件
FILE = 'artifacts/test_dataset.csv'  # 定义数据文件路径
df = pd.read_csv(FILE)  # 读取csv文件

# 打乱数据顺序
df = df.sample(frac=1, random_state=42).reset_index(drop=True)  # 打乱数据顺序并重置索引
print("数据预览：")
print(df.head())  # 打印数据的前五行

# 可视化Botnet Family的分布
plt.figure(figsize=(12, 6))  # 设置画布大小
sns.countplot(x='Botnet_Family', data=df)  # 绘制Botnet Family的类别分布图
plt.xticks(rotation=90)  # 旋转x轴标签，以避免重叠
plt.title('Botnet Family Distribution')  # 设置图表标题
plt.show()  # 显示图表

# 文本预处理
tokenizer = Tokenizer(char_level=True)  # 创建Tokenizer对象，设置char_level=True表示按字符进行分词
tokenizer.fit_on_texts(df['Domain'])  # 基于域名列生成词汇表

# 将域名转换为序列
sequences = tokenizer.texts_to_sequences(df['Domain'])  # 将文本数据转换为数字序列

# 填充序列，使所有序列的长度一致
X = pad_sequences(sequences, maxlen=50, padding='post')  # 最大长度50，后填充

print(f"词汇表大小: {len(tokenizer.word_index)}")  # 打印词汇表的大小

# 标签编码
label_encoder = LabelEncoder()  # 创建标签编码器
df['Botnet_Family'] = label_encoder.fit_transform(df['Botnet_Family'])  # 对标签进行编码

# 将标签转换为独热编码
y = to_categorical(df['Botnet_Family'])  # 将标签转换为独热编码形式

# 划分训练集和测试集
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y  # 80%训练集，20%测试集，按标签分层抽样
)

print(f"训练集样本数: {X_train.shape[0]}")  # 打印训练集样本数
print(f"测试集样本数: {X_test.shape[0]}")  # 打印测试集样本数

# 构建模型
# Input layer
input_seq = Input(shape=(50,))  # 输入层，输入形状为(50,)，即每个输入序列长度为50

# Embedding layer
# 修改input，新版keras不需要手动输入input
embedded = Embedding(input_dim=len(tokenizer.word_index) + 1,  # 设置词汇表大小（加1是因为索引从1开始）
                    output_dim=192,  # 设置嵌入向量的维度
                    input_length=50)(input_seq)  # 设置输入序列的长度

# 第一组卷积层
conv1 = Conv1D(filters=256, kernel_size=7, activation='relu')(embedded)  # 卷积层，使用7个大小的卷积核，激活函数为ReLU
pool1 = MaxPooling1D(pool_size=2)(conv1)  # 最大池化层，池化窗口大小为2
drop1 = Dropout(0.25)(pool1)  # Dropout层，防止过拟合，丢弃率为25%

# 第二组卷积层
conv2 = Conv1D(filters=128, kernel_size=5, activation='relu')(drop1)  # 卷积层，使用5个大小的卷积核，激活函数为ReLU
pool2 = MaxPooling1D(pool_size=2)(conv2)  # 最大池化层，池化窗口大小为2
drop2 = Dropout(0.25)(pool2)  # Dropout层，丢弃率为25%

# Multi-Head Self-Attention layer
attention_output = MultiHeadAttention(num_heads=4, key_dim=128)(drop2, drop2)  # 多头自注意力层，4个头，128维度
attention_output = Add()([attention_output, drop2])  # 残差连接，将注意力输出与输入相加
attention_output = LayerNormalization()(attention_output)  # 归一化层

# Flatten and Dense layers
flatten = Flatten()(attention_output)  # 将输出展平为一维
dense1 = Dense(128, activation='relu')(flatten)  # 全连接层，128个神经元，激活函数为ReLU
dropout = Dropout(0.25)(dense1)  # Dropout层，丢弃率为25%
output = Dense(y.shape[1], activation='softmax')(dropout)  # 输出层，使用softmax激活函数，输出类别数为标签的类别数

# 创建模型
model1 = Model(inputs=input_seq, outputs=output)  # 构建模型

# 编译模型
model1.compile(optimizer='adam',  # 优化器使用Adam
               loss='categorical_crossentropy',  # 损失函数使用多类别交叉熵
               metrics=['accuracy'])  # 评估指标使用准确率

# 设置回调函数
early_stopping = EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)  # 设置早停，监控验证集损失，耐心值为3
reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=2, min_lr=0.0001)  # 设置学习率衰减，验证集损失下降时降低学习率

# 训练模型
history = model1.fit(
    X_train, y_train, 
    epochs=100,  # 最大训练轮次为100
    batch_size=64,  # 每批次64个样本
    validation_split=0.2,  # 使用20%的训练数据作为验证集
    callbacks=[early_stopping, reduce_lr]  # 设置回调函数
)

# 绘制训练过程中的损失和准确率
plt.figure(figsize=(12, 5))  # 设置图形大小

# 损失曲线
plt.subplot(1, 2, 1)  # 创建第一个子图
plt.plot(history.history['loss'], label='训练损失')  # 绘制训练损失曲线
plt.plot(history.history['val_loss'], label='验证损失')  # 绘制验证损失曲线
plt.xlabel('Epoch')  # X轴标签
plt.ylabel('损失')  # Y轴标签
plt.title('损失曲线')  # 标题
plt.legend()  # 显示图例

# 准确率曲线
plt.subplot(1, 2, 2)  # 创建第二个子图
plt.plot(history.history['accuracy'], label='训练准确率')  # 绘制训练准确率曲线
plt.plot(history.history['val_accuracy'], label='验证准确率')  # 绘制验证准确率曲线
plt.xlabel('Epoch')  # X轴标签
plt.ylabel('准确率')  # Y轴标签
plt.title('准确率曲线')  # 标题
plt.legend()  # 显示图例

plt.tight_layout()  # 调整布局
plt.show()  # 显示图表

# 评估模型
loss, accuracy = model1.evaluate(X_test, y_test)  # 评估模型在测试集上的表现
print('测试损失:', loss)  # 打印测试集损失
print('测试准确率:', accuracy)  # 打印测试集准确率

# 进行预测并生成分类报告和混淆矩阵
print("\n进行预测并生成分类报告和混淆矩阵...")
y_pred = model1.predict(X_test)  # 使用模型对测试集进行预测
y_pred_classes = np.argmax(y_pred, axis=1)  # 获取预测类别
y_true = np.argmax(y_test, axis=1)  # 获取真实类别

# 分类报告
print("\n分类报告:")
print(classification_report(y_true, y_pred_classes, target_names=label_encoder.classes_))  # 打印分类报告

# 混淆矩阵
cm = confusion_matrix(y_true, y_pred_classes)  # 计算混淆矩阵
plt.figure(figsize=(12, 10))  # 设置图表大小
sns.heatmap(cm, annot=True, fmt='d', xticklabels=label_encoder.classes_, yticklabels=label_encoder.classes_, cmap='Blues')  # 绘制混淆矩阵热图
plt.ylabel('实际类别')  # 设置Y轴标签
plt.xlabel('预测类别')  # 设置X轴标签
plt.title('混淆矩阵')  # 设置标题
plt.show()  # 显示图表

# 保存模型和预处理工具（如果需要）
# joblib.dump(tokenizer, 'tokenizer.pkl')  # 保存Tokenizer对象
# joblib.dump(label_encoder, 'encoder_multi.pkl')  # 保存LabelEncoder对象
# model1.save('multiclass_classification_model.h5')  # 保存Keras模型

print("模型和预处理工具已保存")  # 打印模型保存完成的提示
