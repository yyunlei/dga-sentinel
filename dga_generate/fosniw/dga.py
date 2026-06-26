import argparse
import os

PATTERNS = {
    "koreasys": "appx.koreasys{}.com",
    "winsoft": "app2.winsoft{}.com"
}

def dga(prefix, num_domains):
    """
    根据给定的前缀生成指定数量的域名
    """
    pattern = PATTERNS.get(prefix)
    if not pattern:
        raise ValueError(f"unsupported pattern {prefix}")

    domains = []  # 用于保存生成的域名
    for i in range(num_domains):
        domain = pattern.format(i)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", choices=["winsoft", "koreasys"], default="winsoft", help="选择域名前缀")
    parser.add_argument("-n", "--num", type=int, default=20000, help="生成的域名数量，默认20000")
    args = parser.parse_args()

    # 获取生成的域名数量
    num_domains = args.num

    # 生成域名
    domains = dga(args.prefix, num_domains)

    # 将生成的域名写入文件
    write_domains_to_file(domains)
