import argparse
import os

class RandInt:

    def __init__(self, seed):
        self.seed = seed

    def rand_int_modulus(self, modulus):
        ix = self.seed
        ix = 16807*(ix % 127773) - 2836*(ix // 127773) & 0xFFFFFFFF
        self.seed = ix
        return ix % modulus

def get_domains(seed, nr):
    r = RandInt(seed)
    for _ in range(nr):
        domain_len = r.rand_int_modulus(12+1) + 8  # Random domain length between 8 and 20
        domain = ""
        for _ in range(domain_len):
            char = chr(ord('a') + r.rand_int_modulus(25+1))  # Random character a-z
            domain += char
        domain += ".com"
        yield domain

def write_domains_to_file(domains, filename='domains.txt'):
    """
    将生成的域名写入到文件中。
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
    parser = argparse.ArgumentParser(description="generate Dircrypt domains")
    parser.add_argument("seed", help="seed as hex")
    parser.add_argument("-n", "--nr", help="Number of domains to generate", type=int, default=20000)
    args = parser.parse_args()

    domains = list(get_domains(int(args.seed, 16), args.nr))

    # 将生成的域名写入文件
    write_domains_to_file(domains, filename='domains.txt')
