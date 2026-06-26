import hashlib
import struct
import argparse
from datetime import datetime
from itertools import chain
import os

# 配置字典
configs = {
    "kz_v1": {
        "conso_a": "bcdfghjklmnpqrstvwx",
        "conso_b": "zxtsrqpnmlkgfdc",
        "vowels_a": "aeiou",
        "vowels_b": "aio",
        "mod": 7,
        "mod2": 1,
        "tld": "kz"
    },
    "com_v1": {
        "conso_a": "bcdfghjklmnpqrstvwx",
        "conso_b": "zxtsrqpnmlkgfdc",
        "vowels_a": "aeiou",
        "vowels_b": "aio",
        "mod": 7,
        "mod2": 1,
        "tld": "com"
    }, 
    "kz_v2": {
        "conso_a": "kqbhcndjfwglpmzxrsv", 
        "conso_b": "qzlbtgrnkxsfdcm",
        "vowels_a": "aeiou",
        "vowels_b": "aio",
        "mod": 8,
        "mod2": 2,
        "tld": "kz"
    }
}

# 根据提供的r和config计算域名的一部分
def part(r, c):
    config = configs[c]
    mod = config.get("mod")
    mod2 = config.get("mod2")
    conso_a = config.get('conso_a')
    conso_b = config.get('conso_b')
    vowels_a = config.get('vowels_a')
    vowels_b = config.get('vowels_b')
    assert(len(conso_a) == 19)
    assert(len(vowels_a) == 5)
    assert(len(vowels_b) == 3)
    assert(len(conso_b) == 15)

    string = ""
    string += conso_a[r % 19]
    rp2 = r + 2
    string += vowels_a[((r+1) & 0xFF) % 5]
    if string[1] == 'e' and rp2 & mod:
        v = vowels_b[rp2 % 3]
    else:
        if not (rp2 & mod2):
            return string
        v = conso_b[(r+3) % 15]
    string += v
    return string

# 基于md5哈希和config生成域名
def dga(md5, length, config, loops=16):
    domain = ""
    for i in range(loops):
        r = md5[i]
        p = part(r, config)
        domain += p
        if len(domain) >= length:
            domain = domain[:length]
            domain += "." + configs[config]["tld"]
            return domain

# 计算自纪元以来的天数
def days_since_0(d):
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    year = d.year
    month = d.month - 1
    day = d.day
    if not year % 4:
        days_in_month[1] = 29
    t = 0
    while month > 0:
        t += days_in_month[month]
        month -= 1
    return day + t + 365*(year - year//4) + 366*(year//4)

# 生成指定日期的域名
def domains_for_day(r, config):
    count = 0
    for i in range(100):  # 增加生成数量，每次生成100个域名
        b = struct.pack("<I", r)
        md5 = hashlib.md5(b).digest()
        r = struct.unpack("<I", md5[:4])[0]
        length = (r & 3) + 9
        domain = dga(md5, length, config)
        r += 1
        yield domain
        count += 1

# 生成域名直到满足20000个
def generate_domains(date, config, target_count=20000):
    days = days_since_0(date)
    count = 0
    for j in chain(range(0, -200, -1), range(1, 100)):  # 扩大范围
        if count >= target_count:
            break
        for domain in domains_for_day(days + j, config):
            if count >= target_count:
                break
            yield domain
            count += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="gozi dga")
    parser.add_argument("-c", "--config", default="kz_v1", choices=list(configs.keys()))
    parser.add_argument("-d", "--date", 
            help="date for which to generate domains")
    args = parser.parse_args()
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 获取当前脚本的路径并生成文件路径
    script_dir = os.path.dirname(os.path.realpath(__file__))  # 当前脚本所在的目录
    output_file_path = os.path.join(script_dir, "domains.txt")

    # 打开文件以写入域名
    with open(output_file_path, "w") as f:
        for domain in generate_domains(d, args.config):
            f.write(domain + "\n")

    print(f"域名已生成并写入: {output_file_path}")
