import argparse
from ctypes import c_int
import os

class Rand:

    def __init__(self):
        self.r = c_int()

    def srand(self, seed):
        self.r.value = seed

    def rand(self):
        self.r.value = 214013 * self.r.value + 2531011
        return (self.r.value >> 16) & 0x7FFF

    def randint(self, lower, upper):
        return lower + self.rand() % (upper - lower + 1)

def dga(r):
    """
    生成一个域名
    """
    sld = ''.join([chr(r.randint(ord('a'), ord('z'))) for _ in range(10)])
    return sld + '.com'

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
    parser = argparse.ArgumentParser(description="生成随机的DGA域名")
    parser.add_argument("seed", type=int, help="随机种子")
    parser.add_argument("-n", "--num", type=int, default=20000, help="生成的域名数量，默认为20000")
    args = parser.parse_args()

    r = Rand()
    r.srand(args.seed)

    # 生成所需数量的域名
    domains = [dga(r) for _ in range(args.num)]

    # 将生成的域名写入到文件
    write_domains_to_file(domains)
