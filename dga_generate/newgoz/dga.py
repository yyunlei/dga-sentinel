import hashlib
from datetime import datetime, timedelta
import struct
import argparse
import os  # 导入os模块，用于处理文件路径

def get_seed(seq_nr, date):
    key = "\x01\x05\x19\x35"
    seq_nr = struct.pack('<I', seq_nr) 
    year = struct.pack('<H', date.year)
    month = struct.pack('<H', date.month)
    day = struct.pack('<H', date.day)
    m = hashlib.md5()
    m.update(seq_nr)
    m.update(year)
    m.update(key.encode('latin1'))
    m.update(month)
    m.update(key.encode('latin1'))
    m.update(day)
    m.update(key.encode('latin1'))
    return m.hexdigest()

def create_domain(seq_nr, date):
    def generate_domain_part(seed, nr):
        part = [] 
        for i in range(nr-1):
            edx = seed % 36
            seed //= 36
            if edx > 9:
                char = chr(ord('a') + (edx-10))
            else:
                char = chr(edx + ord('0'))
            part += char
            if seed == 0:
                break
        part = part[::-1]
        return ''.join(part)    

    def hex_to_int(seed):
        indices = range(0, 8, 2)
        data = [seed[x:x+2] for x in indices]
        seed = ''.join(reversed(data))
        return int(seed,16)

    seed_value = get_seed(seq_nr, date)
    domain = ""
    for i in range(0, 16, 4):
        seed = seed_value[i*2:i*2+8]
        seed = hex_to_int(seed)
        domain += generate_domain_part(seed, 8)
    if seq_nr % 4 == 0:
        domain += ".com"
    elif seq_nr % 3 == 0:
        domain += ".org"
    elif seq_nr % 2 == 0:
        domain += ".biz"
    else:
        domain += ".net"
    return domain

def main():
    """
    主函数，解析命令行参数，生成DGA域名，并将其写入文件。
    """
    parser = argparse.ArgumentParser(description="Generate DGA domains and save to domains.txt")
    parser.add_argument(
        "-d", "--date",
        help="Specify the date as YYYY-mm-dd. If not provided, current date is used.",
        type=str
    )
    parser.add_argument(
        "-n", "--nr", type=int, default=20000,
        help="Number of domains to generate (default: 1000)."
    )
    args = parser.parse_args()

    # 解析日期参数
    date_str = args.date
    if date_str:
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("[-] Invalid date format. Please use YYYY-mm-dd.")
            return
    else:
        date = datetime.now()  # 使用当前日期

    # 获取脚本所在的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, 'domains.txt')  # 构建输出文件路径

    # 打开文件以写入模式
    try:
        with open(output_file, 'w') as f:
            for seq_nr in range(args.nr):  # 生成指定数量的域名
                domain = create_domain(seq_nr, date)
                f.write(domain + '\n')  # 将域名写入文件
        print(f"[+] Successfully generated {args.nr} domains and saved to '{output_file}'.")
    except IOError as e:
        print(f"[-] Failed to write to file '{output_file}'. Error: {e}")

if __name__ == "__main__":
    main()
