import argparse
import os

def half_until_smaller_equal_24(nr):
    """
    将数字右移直到它小于或等于 24。
    """
    while nr > 24:
        nr = nr >> 1
    return nr

def getchar(nr):
    """
    获取对应字符，将数字转化为字母，确保字符索引不超过24。
    """
    return chr(half_until_smaller_equal_24(nr) + ord('a'))

def gettld(nr):
    """
    根据数字生成顶级域名。
    """
    index = half_until_smaller_equal_24(nr) // 5
    tlds = [".com", ".org", ".net", ".ru", ".in"]
    return tlds[index]

def dga(prefix, nr_of_domains=20000):
    """
    生成指定数量的DGA域名。
    """
    if prefix == "sn":
        primes = [1, 7, 3, 5, 11, 13]
    else:
        primes = [1, 3, 5, 7, 11, 13]
    
    # 生成 nr_of_domains 个域名
    for nr in range(1, nr_of_domains + 1):
        domain = prefix 
        for prime in primes: 
            domain += getchar(prime * nr)
        domain += gettld(nr)
        yield domain

def write_domains_to_file(domains, filename="domains.txt"):
    """
    将生成的域名写入到文件
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    with open(file_path, 'w') as file:
        for domain in domains:
            file.write(domain + '\n')
    print(f"已生成并保存 {len(domains)} 个域名到 {file_path} 文件。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", choices=["sn", "al"], help="选择前缀 'sn' 或 'al'")
    parser.add_argument("-n", "--num", type=int, default=20000, help="生成的域名数量，默认为20000")
    args = parser.parse_args()

    # 生成DGA域名
    domains = list(dga(args.prefix, nr_of_domains=args.num))

    # 将生成的域名写入到文件
    write_domains_to_file(domains)
