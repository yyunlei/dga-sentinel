import hashlib
from datetime import datetime, timedelta
import argparse
import os


def dga(date):
    generated_count = 0  # 用于跟踪已生成的域名数量

    # 循环生成域名直到生成 20,000 个
    while generated_count < 20000:
        for index in range(1020):
            seed = [0] * 7
            seed[0] = ((date.year & 0xFF) + 0x30) & 0xFF
            seed[1] = date.month 
            seed[2] = (date.day // 7) * 7  # 将日期按7天一组
            r = index
            for i in range(4):
                seed[3 + i] = r & 0xFF
                r >>= 8

            seed_str = "".join(chr(s) for s in seed)

            m = hashlib.md5()
            m.update(seed_str.encode('latin1'))
            md5 = m.digest()

            domain = ""
            for m in md5:
                d = (m & 0x1F) + ord('a')
                c = (m >> 3) + ord('a')
                if d != c:
                    if d <= ord('z'):
                        domain += chr(d)
                    if c <= ord('z'):
                        domain += chr(c)

            tlds = [".ru", ".biz", ".info", ".org", ".net", ".com"]
            for i, tld in enumerate(tlds): 
                m = len(tlds) - i
                if not index % m:
                    domain += tld
                    break

            # 输出生成的域名
            yield domain
            generated_count += 1
            if generated_count >= 20000:
                return  # 如果生成 20,000 个域名，退出循环


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", help="date for which to generate domains")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 获取脚本所在的目录路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 设置输出文件路径
    outfile_path = os.path.join(script_dir, 'domains.txt')

    # 打开文件并写入 20,000 个域名
    with open(outfile_path, 'w') as f:
        for domain in dga(d):
            f.write(domain + "\n")

    print(f"20,000个域名已生成并写入 {outfile_path} 文件中。")
