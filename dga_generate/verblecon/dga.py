import argparse
import hashlib
from datetime import datetime
from typing import Iterator


def dga(date: datetime, seed: str, num_domains: int) -> Iterator[str]:
    data = f"{date.strftime('%Y-%m-%d')}{seed}".encode("ascii")
    sld = hashlib.md5(data).hexdigest()

    # 生成域名并输出
    for _ in range(num_domains):
        yield f"{sld}.tk"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DGA of MyDoom")
    parser.add_argument(
        "-d", "--date", help="date for which to generate domains, e.g., 2022-05-09"
    )
    parser.add_argument("-s", "--seed", help="DGA seed", default="verble")
    args = parser.parse_args()
    
    # 获取日期
    if args.date:
        date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        date = datetime.now()

    # 设置生成域名的数量
    num_domains = 20000

    # 打开文件并将域名写入
    with open("domains.txt", "w") as file:
        for domain in dga(date=date, seed=args.seed, num_domains=num_domains):
            file.write(domain + "\n")

    print(f"{num_domains} domains have been written to 'domains.txt'")
