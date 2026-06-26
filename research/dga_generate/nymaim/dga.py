import argparse
from datetime import datetime
import os  # 导入os模块，用于处理文件路径


class PRNG:

    def __init__(self, date):
        s = date.year + (date.month << 16) + (date.isoweekday() % 7) \
                + (date.day << 16) 
        self.r = 4*[None]
        self.r[0] = (s + 0x52455641) & 0xFFFFFFFF
        self.r[1] = (s + 0x49484F4C) 
        self.r[1] = self.r[1] if self.r[1] <= 0xFFFFFFFF else 0
        self.r[2] = (s + 0x59554820) & 0xFFFFFFFF
        self.r[3] = (s + 0x4D415620) & 0xFFFFFFFF

    def rand(self, m):
        t = 4*[None]

        t[0] = ((self.r[0] << 11) ^ self.r[0]) & 0xFFFFFFFF
        t[1] = self.r[1]
        t[2] = self.r[2]
        t[3] = ((self.r[3] >> 19) ^ self.r[3]) ^ t[0]
        t[0] = t[0] >> 8
        t[3] = t[3] ^ t[0]

        c = self.r[2]
        for i in range(3):
            self.r[i] = (self.r[i] + self.r[i+1]) & 0xFFFFFFFF
        self.r[3] = t[3]

        nr = (((c + t[3]) & 0xFFFFFFFF)//100) % m
        return nr

def dga(date, nr):
    r = PRNG(date) 

    # 获取脚本所在的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, 'domains.txt')  # 构建输出文件路径

    # 打开文件以写入模式
    try:
        with open(output_file, 'w') as f:
            for i in range(nr):
                length = r.rand(6) + 6
                domain = ""
                for l in range(length):
                    domain += chr(ord('a') + (r.rand(26) % 26))

                t = ord(domain[-2]) - ord('a') 
                if t < 9: 
                    domain += '.com'
                elif t < 13:
                    domain += '.org'
                elif t < 17:
                    domain += '.biz'
                elif t < 21:
                    domain += '.net'
                else:
                    domain += '.info'

                f.write(domain + '\n')  # 将域名写入文件

        print(f"[+] Successfully generated {nr} domains and saved to '{output_file}'.")
    except IOError as e:
        print(f"[-] Failed to write to file '{output_file}'. Error: {e}")

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", help="as YYYY-MM-DD")
    parser.add_argument("-n", "--nr", help="nr of domains", type=int, default=20000)
    args = parser.parse_args()
    date_str = args.date
    if date_str:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        date = datetime.now() 

    dga(date, args.nr)
