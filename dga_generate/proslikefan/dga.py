import argparse
import os
from ctypes import c_int
from datetime import datetime

def dga(date, magic, tlds, output_file):
    # 用于生成域名并写入文件
    count = 0
    while count < 20000:
        for tld in tlds:
            seed_string = '.'.join([str(s) for s in 
                    [magic, date.month, date.day, date.year, tld]])
            r = abs(hash_string(seed_string))
            domain = ""
            k = 0
            while(k < r % 7 + 6):  # 控制域名长度
                r = abs(hash_string(domain + str(r))) 
                domain += chr(r % 26 + ord('a')) 
                k += 1
            domain += '.' + tld
            output_file.write(domain + "\n")  # 写入文件
            count += 1
            if count >= 20000:
                break


def hash_string(s):
    h = c_int(0) 
    for c in s:
        h.value = (h.value << 5) - h.value + ord(c)
    return h.value


if __name__ == "__main__":
    """ known magic seeds are "prospect" and "OK" """
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", help="date for which to generate domains")
    parser.add_argument("-m", "--magic", help="magic string", 
            default="prospect")
    parser.add_argument("-t", "--tlds", nargs="+", help="tlds",
        default=["eu", "biz", "se", "info", "com", "net", "org", "ru", "in", "name"])
    args = parser.parse_args()

    # 获取日期
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 获取当前脚本的路径并生成文件路径
    script_dir = os.path.dirname(os.path.realpath(__file__))  # 当前脚本所在的目录
    output_file_path = os.path.join(script_dir, "domains.txt")

    # 打开文件以写入域名
    with open(output_file_path, "w") as f:
        dga(d, args.magic, args.tlds, f)

    print(f"域名已生成并写入: {output_file_path}")
