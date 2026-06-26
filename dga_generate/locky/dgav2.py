import argparse
from datetime import datetime
import os

config = {
    1: {
        'seed': 62,
        'shift': 7,
        'mod': 8,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    },
    2: {
        'seed': 75,
        'shift': 7,
        'mod': 8,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    },
    3: {
        'seed': 9,
        'shift': 7,
        'mod': 8,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    },
    4: {
        'seed': 7,
        'shift': 7,
        'mod': 8,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    },
    5: {
        'seed': 0,
        'shift': 5,
        'mod': 6,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    },
    6: {
        'seed': 660,
        'shift': 7,
        'mod': 8,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    },
    7: {
        'seed': 555,
        'shift': 7,
        'mod': 8,
        'tlds': ['ru', 'pw', 'eu', 'in', 'yt', 'pm', 'us', 'fr', 'de',
                 'it', 'be', 'uk', 'nl', 'tf']
    }
}

def ror32(v, s):
    v &= 0xFFFFFFFF
    return ((v >> s) | (v << (32 - s))) & 0xFFFFFFFF

def rol32(v, s):
    return ((v << s) | (v >> (32 - s))) & 0xFFFFFFFF

def dga(date, config_nr, domain_nr):
    c = config[config_nr]

    t = ror32(0xB11924E1 * (date.year + 0x1BF5), c['shift'])
    if c['seed']:
        t = ror32(0xB11924E1 * (t + c['seed'] + 0x27100001), c['shift'])
    t = ror32(0xB11924E1 * (t + (date.day // 2) + 0x27100001), c['shift'])
    t = ror32(0xB11924E1 * (t + date.month + 0x2709A354), c['shift'])

    nr = rol32(domain_nr % c['mod'], 21)
    s = rol32(c['seed'], 17)

    r = (ror32(0xB11924E1 * (nr + t + s + 0x27100001), c['shift']) + 0x27100001) & 0xFFFFFFFF

    length = (r % 11) + 5

    domain = ""
    for i in range(length):
        r = (ror32(0xB11924E1 * rol32(r, i), c['shift']) + 0x27100001) & 0xFFFFFFFF
        domain += chr(r % 25 + ord('a'))
    domain += '.'
    r = ror32(r * 0xB11924E1, c['shift'])
    tlds = c['tlds']
    tld_i = ((r + 0x27100001) & 0xffffffff) % len(tlds)
    domain += tlds[tld_i]
    return domain

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date",
                        help="date for which to generate domains")
    parser.add_argument("-c", "--config", choices=list(range(1, 8)),
                        help="config nr", type=int, default=1)
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建 output 文件路径
    outfile_path = os.path.join(script_dir, 'domains.txt')

    # 打开文件并写入域名
    with open(outfile_path, 'w') as f:
        for i in range(20000):
            f.write(dga(d, args.config, i) + "\n")

    print(f"域名已生成并写入 {outfile_path} 文件中。")
