import os
import csv

def map_to_lowercase_letter(s):
    return ord('a') + ((s - ord('a')) % 26)

def next_domain(domain):
    dl = [ord(x) for x in domain]
    dl[0] = map_to_lowercase_letter(dl[0] + dl[3])
    dl[1] = map_to_lowercase_letter(dl[0] + 2*dl[1])
    dl[2] = map_to_lowercase_letter(dl[0] + dl[2] - 1)
    dl[3] = map_to_lowercase_letter(dl[1] + dl[2] + dl[3])
    return ''.join([chr(x) for x in dl])

# 初始域名
seed = 'hosdfndsgbitttgapoalohax.com'  # 初始域名
domain = seed

# 获取当前脚本所在目录
current_directory = os.path.dirname(os.path.abspath(__file__))
csv_file_path = os.path.join(current_directory, 'domains.csv')

# 创建并写入CSV文件
with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow(['Domain', 'Label', 'Value'])  # 写入表头
    
    for i in range(20000):
        csv_writer.writerow([domain, 'banjori', 1])  # 写入数据行
        domain = next_domain(domain)

print(f"域名已生成并写入到 {csv_file_path} 文件中。")
