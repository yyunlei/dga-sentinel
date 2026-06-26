import argparse
from datetime import datetime
import os

def init_rand_and_chars(year, month, day, nr_b, r):
    r = (r + year + ((nr_b << 16) + (month << 8) | day)) & 0xFFFFFFFF
    charset = [chr(x) for x in range(ord('a'), ord('z'))] +\
            [chr(x) for x in range(ord('0'), ord('9'))]
            
    return charset, r

def generate_domain(charset, r):
    len_l = 0xC
    len_u = 0x18
    r = (1664525*r + 1013904223) & 0xFFFFFFFF
    domain_len = len_l + r % (len_u - len_l)
    domain = ""
    for i in range(domain_len, 0, -1):
        r = ((1664525 * r) + 1013904223) & 0xFFFFFFFF
        domain += charset[r % len(charset)] 
    domain += ".ddns.net"
    return domain, r

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
    parser.add_argument("-s", "--seed", help="seed", default="1DBA8930")
    parser.add_argument("-d", "--date", help="date for which to generate domains")
    parser.add_argument("-t", "--debug", help="debug DGA (day set to 8)")
    parser.add_argument("-n", "--nr", help="nr of domains to generate", 
           type=int, default=20000)
    args = parser.parse_args()
    
    d = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    day = 8 if args.debug else d.day

    charset, r = init_rand_and_chars(d.year, d.month, day, 1, 
            int(args.seed, 16)) 

    # 生成域名并存储在列表中
    domains = []
    for _ in range(args.nr):
        domain, r = generate_domain(charset, r)
        domains.append(domain)

    # 将域名写入文件
    write_domains_to_file(domains, filename='domains.txt')
