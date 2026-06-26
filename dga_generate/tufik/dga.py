import argparse
import hashlib
import struct
from ctypes import c_ubyte
from datetime import datetime

# 哈希处理函数
def hash_data(data: bytearray) -> bytearray:
    return bytearray(hashlib.md5(data).digest())

# 根据索引生成TLD
def idx_to_tld(idx: int) -> str:
    if not idx % 5:
        return "biz"
    if not idx % 4:
        return "info"
    if not idx % 3:
        return "org"
    if not idx % 2:
        return "net"
    else:
        return "com"

# 字节求和
def sum_bytes(data: bytearray) -> bytearray:
    res = bytearray()
    for d in data:
        res.append((d & 0x0F) + ((d & 0xF0) >> 4))
    return res

# 生成种子数据
def seed_data(date: datetime, idx: int) -> bytearray:
    data = bytearray(8)
    data[0] = c_ubyte(date.year + 48).value  # 年份
    data[1] = date.month  # 月份
    data[2] = date.day  # 日期
    data[4:8] = struct.pack("<I", idx & 0xFFFFFFFE)  # 额外的种子数据
    return data

# 加密种子
def encrypt_seed(data: bytearray, key: int) -> bytearray:
    key_bytes = struct.pack("<I", key)
    for i, d in enumerate(data):
        data[i] ^= key_bytes[i % 4]
    return data

# 将字节数组转换为SLD
def sums_to_sld(data: bytearray) -> str:
    sld = ""
    for b in data:
        cc = ord("a") + b
        if cc <= ord("z"):
            sld += chr(cc)
    return sld

# DGA算法
def dga(date: datetime = None, magic: int = 0x997722ED, num_domains: int = 20000):
    generated_domains = 0
    idx = 0
    while generated_domains < num_domains:
        seed = seed_data(date=date, idx=idx)
        enc_seed = encrypt_seed(data=seed, key=magic)
        hashed_seed = hash_data(data=enc_seed)
        summed_seed = sum_bytes(data=hashed_seed)
        sld = sums_to_sld(data=summed_seed)
        tld = idx_to_tld(idx)
        yield f"{sld}.{tld}"
        idx += 1
        generated_domains += 1

# 主函数
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DGA of Tufik")
    parser.add_argument(
        "-d", "--date", help="date for which to generate domains, e.g., 2022-05-09"
    )

    parser.add_argument(
        "-m", "--magic", choices=["0x997722ED"], default="0x997722ED", help="magic seed"
    )
    args = parser.parse_args()

    # 处理日期参数
    d = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    magic = int(args.magic, 16)

    # 打开文件写入域名
    with open('domains.txt', 'w') as f:
        for domain in dga(date=d, magic=magic, num_domains=20000):
            f.write(domain + '\n')

    print("20000 domains have been written to 'domains.txt'")
