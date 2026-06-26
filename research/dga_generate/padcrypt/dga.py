import argparse
import hashlib
from datetime import datetime
import os

configs = {
    "2.2.86.1" : {
        'nr_domains': 24,
        'tlds': ['com', 'co.uk', 'de', 'org', 'net', 'eu', 'info', 'online',
            'co', 'cc', 'website'],
        'digit_mapping': "abcdnfolmk",
        'separator': ':',
        },
    "2.2.97.0" : {
        'nr_domains': 24*3,
        'tlds': ['com', 'co.uk', 'de', 'org', 'net', 'eu', 'info', 'online',
            'co', 'cc', 'website'],
        'digit_mapping': "abcdnfolmk",
        'separator': '|'
        }
}

def dga(date, config_nr, nr_domains=None):
    config = configs[config_nr]
    dm = config['digit_mapping']
    tlds = config['tlds']
    
    # 如果命令行参数中指定了生成的域名数量，则覆盖配置中的数量
    nr_domains = nr_domains or config['nr_domains']

    for i in range(nr_domains):
        seed_str = "{}-{}-{}{}{}".format(date.day, date.month, date.year,
                config['separator'], i)
        h = hashlib.sha256(seed_str.encode('ascii')).hexdigest()
        domain = ""
        for hh in h[3:16+3]:
            domain += dm[int(hh)] if '0' <= hh <= '9' else hh
        tld_index = int(h[-1], 16)
        tld_index = 0 if tld_index >= len(tlds) else tld_index
        domain += "." + config['tlds'][tld_index]
        yield domain

def date_parser(s):
    return datetime.strptime(s, "%Y-%m-%d")

if __name__=="__main__":
    now = datetime.now().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="DGA for PadCrypt ransomware")
    parser.add_argument(
        "-d", "--date",
        help="Date for which to generate domains, e.g., 2022-05-09",
        default=now,
        type=date_parser
    )
    parser.add_argument(
        "-v", "--version",
        help="DGA version",
        choices=["2.2.86.1", "2.2.97.0"],
        default="2.2.86.1"
    )
    parser.add_argument(
        "-n", "--nr",
        help="Number of domains to generate",
        type=int,
        default=None
    )
    args = parser.parse_args()

    # 获取当前脚本目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, 'domains.txt')  # 文件输出路径

    try:
        # 打开文件准备写入域名
        with open(output_file, 'w') as f:
            for domain in dga(args.date, args.version, args.nr):
                f.write(domain + '\n')
        print(f"[+] Successfully generated {args.nr if args.nr else configs[args.version]['nr_domains']} domains and saved to '{output_file}'.")
    except IOError as e:
        print(f"[-] Failed to write to file '{output_file}'. Error: {e}")
