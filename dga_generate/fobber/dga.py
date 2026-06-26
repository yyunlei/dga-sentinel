import argparse
import os

def ror32(v, n):
    return ((v >> n) | (v << (32 - n))) & 0xFFFFFFFF

def next_domain(r, c, l, tld):
    domain = ""
    for _ in range(l):
        r = ror32((321167 * r + c) & 0xFFFFFFFF, 16)
        domain += chr((r & 0x17FF) % 26 + ord('a'))

    domain += tld
    return domain, r

def dga(version, num_domains):
    if version == 1:
        r = 0xC87C8A78
        c = -1719405398
        l = 17
        tld = '.net'
    elif version == 2:
        r = 0x851A3E59
        c = -1916503263
        l = 10
        tld = '.com'

    domains = []  # 用来保存生成的域名
    for _ in range(num_domains):
        domain, r = next_domain(r, c, l, tld)
        domains.append(domain)
    
    return domains

def write_domains_to_file(domains, filename="domains.txt"):
    """
    将生成的域名写入到文件
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    with open(file_path, 'w') as file:
        for domain in domains:
            file.write(domain + '\n')
    print(f"已生成并保存 {len(domains)} 个域名到 {file_path} 文件。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DGA of Fobber")
    parser.add_argument("version", choices=[1, 2], type=int, help="选择DGA版本")
    parser.add_argument("-n", "--num", type=int, default=20000, help="生成的域名数量，默认20000")
    args = parser.parse_args()

    # 获取生成域名的数量
    num_domains = args.num

    # 生成域名
    domains = dga(args.version, num_domains)

    # 将生成的域名写入文件
    write_domains_to_file(domains)
