from ctypes import c_uint
import argparse

class Rand():

    def __init__(self, seed):
        self.r = c_uint(seed)
        self.m = 1103515245
        self.a = 12345

    def rand(self):
        self.r.value = self.r.value * self.m + self.a
        self.r.value &= 0x7FFFFFFF
        return self.r.value

# 生成域名的函数
def dga(r):
    length = r.rand() % 5 + 7  # 域名长度为7到11个字符
    domain = ""
    for i in range(length):
        domain += chr(r.rand() % 26 + ord('a'))  # 生成随机字母
    domain += ".top"  # 默认TLD为.top
    return domain

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("seed", help="e.g. DEADBEEF")
    args = parser.parse_args()

    # 使用提供的种子初始化Rand类
    r = Rand(int(args.seed, 16))

    # 目标生成20000个域名
    num_domains = 20000

    # 打开文件并写入域名
    with open("domains.txt", "w") as file:
        for _ in range(num_domains):
            domain = dga(r)  # 生成一个域名
            file.write(domain + "\n")  # 将域名写入文件

    print(f"{num_domains} domains have been written to 'domains.txt'")
