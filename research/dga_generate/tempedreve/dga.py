import string
import argparse
from datetime import datetime, timedelta

def rand(r):
    r = (16843009 * r) & 0xFFFFFFFF
    r = (r + 65805) & 0xFFFFFFFF
    return r

def shuffle(letters, seed):
    r = seed
    for j in range(len(letters)): 
        i = r % len(letters) 
        r = rand(r) 
        letters[j], letters[i] = letters[i], letters[j]
    return letters

def dga(seed, nr_domains):
    tlds = ['.com', '.net', '.org', '.info']
    letters = list(string.ascii_lowercase)
    domains = []
    
    for _ in range(nr_domains):
        letters = shuffle(letters, seed)
        length = seed % 5 + 7
        domain = ""
        r = seed
        for i in range(length):
            domain += letters[r % len(letters)]
            r = rand(r)
        tld = tlds[seed & 3]
        domain += tld
        domains.append(domain)
        seed = rand(seed)  # Change seed to generate a new domain
    
    return domains

def create_seed(date):
    return 10000 * (date.day // 16 * 100 + date.month) + date.year + 42

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", help="date for which to generate domains")
    args = parser.parse_args()
    date_str = args.date
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        d = datetime.now()
    
    # 创建种子
    seed = create_seed(d)
    
    # 生成域名
    nr_domains = 20000
    domains = dga(seed, nr_domains)
    
    # 将生成的域名写入文件
    with open("domains.txt", "w") as file:
        for domain in domains:
            file.write(domain + "\n")
    
    print(f"{nr_domains} domains have been written to 'domains.txt'")
