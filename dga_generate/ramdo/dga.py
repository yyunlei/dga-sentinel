def dga(seed, nr):
    s = (2 * seed * (nr + 1))
    r = s ^ (26 * seed * nr)
    domain = ""
    for i in range(16):  # 生成16个字符的域名
        r = r & 0xFFFFFFFF
        domain += chr(r % 26 + ord('a'))  # 生成a-z之间的字符
        r += (r ^ (s*i**2*26))  # 更新r的值以确保随机性
    
    domain += ".org"  # 后缀固定为".org"
    return domain

def generate_domains(seed, nr_domains):
    domains = []
    nr = 0
    while len(domains) < nr_domains:
        domain = dga(seed, nr)
        domains.append(domain)
        nr += 1  # 增加计数器，确保多次生成
    return domains

# 生成20000个域名
if __name__ == "__main__":
    nr_domains = 20000  # 需要生成的域名数量
    seed = 0xD5FFF  # 种子
    domains = generate_domains(seed, nr_domains)
    
    # 将域名保存到文件
    with open("domains.txt", "w") as f:
        for domain in domains:
            f.write(domain + "\n")
    
    print(f"{nr_domains} 个域名已生成并保存到 'domains.txt' 文件中")
