from datetime import datetime
import argparse
import os

TLDS = ['.com', '.biz', '.us', '.net', '.org', '.ws', '.info']
DEFAULTTLD = ".in"
LETTERS = "asnhreqwpm" 

class Rand:
    def __init__(self, seed):
        self.r = seed

    def rand(self):
        self.r = self.r * 1664525
        self.r += 1013904223
        self.r &= 0xFFFFFFFF
        return self.r

def dga(date, magic, number):
    seed = date.year + date.month + date.day + magic
    r = Rand(seed)

    generated_count = 0  # 生成域名计数器

    while generated_count < number:
        if generated_count == 0x33:
            r = Rand(magic)
        
        v1 = r.rand()
        ra = []
        for i in range(10):
            ra.append(v1 % 10) 
            v1 //= 10

        domain = ""
        for x in ra:
            domain += LETTERS[x]
        
        if ra[0] < len(TLDS):
            tld = TLDS[ra[0]] 
        else:
            tld = DEFAULTTLD

        domain += tld
        yield domain
        
        generated_count += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DGA of MyDoom")
    parser.add_argument("-d", "--date", help="date for which to generate domains, e.g., 2019-04-09")
    parser.add_argument("-m", "--magic", choices=["0xFA8"], default="0xFA8", help="magic seed")
    parser.add_argument("-n", "--number", type=int, default=20000, help="number of domains to generate")
    args = parser.parse_args()

    if args.date:
        date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        date = datetime.now()

    magic = int(args.magic, 16)

    # 获取脚本所在的目录路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 设置输出文件路径
    outfile_path = os.path.join(script_dir, 'domains.txt')

    # 打开文件并写入 20,000 个域名
    with open(outfile_path, 'w') as f:
        for domain in dga(date, magic, args.number):
            f.write(domain + "\n")

    print(f"20,000个域名已生成并写入 {outfile_path} 文件中。")
