#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
#-----------------------------------#
#                                   #
# Conficker-like DGA Domain Generator #
#                                   #
# Purpose: Generate domains similar  #
#          to Conficker's DGA for    #
#          research and educational  #
#          purposes only.            #
#                                   #
# Author: Your Name                  #
# Email: your.email@example.com      #
#                                   #
#-----------------------------------#
"""

import hashlib        # 用于生成哈希值
import datetime       # 用于获取和处理日期
import struct         # 用于处理二进制数据
import os             # 用于文件路径操作

def generate_conficker_domains(seed, date=None, num_domains=20000):
    """
    生成类似Conficker的域名。

    参数:
        seed (str): 用于生成哈希的种子字符串（内部密钥）。
        date (datetime.date): 生成域名的日期。如果为None，则使用当前日期。
        num_domains (int): 要生成的域名数量。

    返回:
        list: 生成的域名列表。
    """
    if date is None:
        date = datetime.date.today()  # 如果未指定日期，则使用今天的日期

    # 常见的顶级域名列表
    tlds = ['.com', '.net', '.org', '.info', '.biz', '.cc', '.su', '.pw']

    # 将日期格式化为字符串，例如 '14052015' 表示 14-05-2015
    formatted_date = date.strftime('%d%m%Y')

    domains = []  # 初始化域名列表

    for i in range(num_domains):
        # 组合种子、日期和索引，生成唯一输入
        input_str = seed + formatted_date + str(i)
        input_bytes = input_str.encode('utf-8')  # 将字符串编码为字节

        # 生成SHA-1哈希
        sha1_hash = hashlib.sha1(input_bytes).digest()

        # 将前8字节（64位）转换为大端整数
        hash_int = struct.unpack('>Q', sha1_hash[:8])[0]

        # 将整数转换为36进制字符串（包含0-9和a-z）
        domain_part = ''
        tmp = hash_int
        while tmp > 0 and len(domain_part) < 8:
            tmp, rem = divmod(tmp, 36)
            if rem < 10:
                domain_part = chr(48 + rem) + domain_part  # '0'-'9'
            else:
                domain_part = chr(97 + (rem - 10)) + domain_part  # 'a'-'z'

        # 填充不足的部分，以确保域名部分长度为8
        domain_part = domain_part.ljust(8, 'a')

        # 选择TLD
        tld = tlds[i % len(tlds)]

        # 组合生成完整域名
        domain = domain_part + tld

        domains.append(domain)  # 添加到域名列表中

    return domains  # 返回生成的域名列表

def write_domains_to_file(domains, filename='domains.txt'):
    """
    将域名列表写入一个文本文件，该文件位于脚本所在的同一目录下。

    参数:
        domains (list): 要写入的域名列表。
        filename (str): 输出文件名。默认为 'domains.txt'。
    """
    # 获取脚本所在的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 构建输出文件的完整路径
    file_path = os.path.join(script_dir, filename)

    try:
        with open(file_path, 'w') as f:
            for domain in domains:
                f.write(domain + '\n')  # 将每个域名写入文件，换行分隔
        print(f"[+] 生成了 {len(domains)} 个域名并保存在 '{file_path}'。")
    except IOError as e:
        print(f"[-] 写入文件 '{file_path}' 时出错: {e}")

def main():
    """
    主函数，生成Conficker-like域名并保存到文件。
    """
    # 定义内部密钥（在实际Conficker中为秘密，不应公开）
    seed = 'ConfickerSecretKey'  # 替换为实际的密钥（如果已知）

    # 获取今天的日期
    today = datetime.date.today()

    # 生成域名
    domains = generate_conficker_domains(seed, date=today, num_domains=20000)

    # 将生成的域名写入文件
    write_domains_to_file(domains, filename='domains.txt')

if __name__ == "__main__":
    main()  # 调用主函数
