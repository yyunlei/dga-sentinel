import base64
import argparse
from datetime import datetime, timedelta
import string
import itertools
import os

def encode(plain: str, key: bytes):
    # base64 encode
    plain = plain.encode('ascii')
    plain = base64.urlsafe_b64encode(plain).decode('ascii')
    tmp = bytearray()

    # XOR encrypt
    for p, k in zip(plain, itertools.cycle(key)): 
        if p in string.ascii_letters:
            p = p.swapcase()
        c = ord(p) ^ k
        tmp.append(c)

    # base64 encode
    cipher = base64.urlsafe_b64encode(tmp).decode('ascii')

    # strip padding
    cipher = cipher.rstrip("=")

    # reverse
    tmp = cipher[::-1]
    return tmp

def dga(seed: str, date: datetime):
    ds = date.strftime("%Y%d")
    sld = encode(ds, seed.encode('ascii'))
    return f"{sld}.com"

def write_domains_to_file(domains, filename='domains.txt'):
    """
    将域名列表写入一个文本文件，该文件位于脚本所在的同一目录下。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)

    try:
        with open(file_path, 'w') as f:
            for domain in domains:
                f.write(domain + '\n')  # 将每个域名写入文件，换行分隔
        print(f"[+] 生成了 {len(domains)} 个域名并保存在 '{file_path}'。")
    except IOError as e:
        print(f"[-] 写入文件 '{file_path}' 时出错: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()    
    parser.add_argument("-d", "--date", help="date for which to generate domains")
    parser.add_argument('-s', '--seed', help='seed for the dga', default="Crackalackin'")
    parser.add_argument('-n', '--nr', help='how many days into the future to generate domains', type=int, default=20000)
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    domains = []
    for i in range(args.nr):
        domains.append(dga(args.seed, d))
        d += timedelta(days=1)

    # 将生成的域名写入文件
    write_domains_to_file(domains, filename='domains.txt')
