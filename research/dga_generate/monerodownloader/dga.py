from datetime import datetime
import hashlib
import argparse

# 顶级域名列表
tlds = [
    ".org",
    ".tickets",
    ".blackfriday",
    ".hosting",
    ".feedback",
]

magic = "jkhhksugrhtijys78g46"
special = "31b4bd31fg1x2"


def dga(date, back=0):
    epoch = datetime(1970, 1, 1)
    days_since_epoch = (date - epoch).days
    days = days_since_epoch
    generated_count = 0  # 用来跟踪生成的域名数量
    while generated_count < 20000:  # 直到生成 20000 个域名
        for j in range(back+1):
            for nr in range(500):
                for tld in tlds:
                    seed = "{}-{}-{}".format(magic, days, nr)
                    m = hashlib.md5(seed.encode('ascii')).hexdigest()
                    mc = m[:13]
                    if nr == 0:
                        sld = special
                    else:
                        sld = mc

                    domain = "{}{}".format(sld, tld)
                    yield domain
                    generated_count += 1
                    if generated_count >= 20000:
                        return  # 达到 20000 个域名后退出
        days -= 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", help="date when domains are generated")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 获取当前脚本所在目录
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建输出文件路径
    outfile_path = os.path.join(script_dir, 'domains.txt')

    # 打开文件并写入 20,000 个域名
    with open(outfile_path, 'w') as f:
        for domain in dga(d):
            f.write(domain + "\n")

    print(f"20,000个域名已生成并写入 {outfile_path} 文件中。")
