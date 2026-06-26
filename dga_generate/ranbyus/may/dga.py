import sys

def dga(day, month, year, seed, nr):
    """
    生成指定数量的域名。

    参数：
        day (int): 日期中的日。
        month (int): 日期中的月。
        year (int): 日期中的年。
        seed (int): 种子值，用于随机数生成。
        nr (int): 要生成的域名数量。

    返回：
        list: 生成的域名列表。
    """
    tlds = ["in", "me", "cc", "su", "tw", "net", "com", "pw", "org"]
    domains = []
    tld_index = day  # 初始化 TLD 索引为 day

    for _ in range(nr):
        domain = []
        for _ in range(14):
            # 执行位运算更新 day, year, month, seed
            day = ((day >> 15) ^ (16 * ((day & 0x1FFF) ^ (4 * (seed ^ day))))) & 0xFFFFFFFF
            year = (((year & 0xFFFFFFF0) << 17) ^ ((year ^ (7 * year)) >> 11)) & 0xFFFFFFFF
            month = (14 * (month & 0xFFFFFFFE) ^ ((month ^ (4 * month)) >> 8)) & 0xFFFFFFFF
            seed = ((seed >> 6) ^ (((day + 8 * seed) << 8) & 0x3FFFF00)) & 0xFFFFFFFF

            # 生成一个字符
            x = ((day ^ month ^ year) % 25) + 97  # 97 是 ASCII 'a' 的码
            domain.append(chr(x))
        
        # 选择 TLD 并生成完整域名
        tld = tlds[tld_index % 8]  # 与 C 代码保持一致，使用 %8
        domain_str = ''.join(domain) + '.' + tld
        domains.append(domain_str)
        tld_index += 1  # 增加 TLD 索引

    return domains

def main():
    """
    主函数，处理命令行参数并调用 dga 函数生成域名。
    """
    if len(sys.argv) != 5:
        print("Usage: dga <day> <month> <year> <seed>")
        print("Example: dga 14 5 2015 b6354bc3")
        sys.exit(1)
    
    try:
        day = int(sys.argv[1])
        month = int(sys.argv[2])
        year = int(sys.argv[3])
        seed_str = sys.argv[4]
        seed = int(seed_str, 16)  # 将十六进制字符串转换为整数
    except ValueError:
        print("Error: Invalid arguments. Ensure day, month, year are integers and seed is a hex string.")
        sys.exit(1)
    
    # 生成域名，数量为40
    domains = dga(day, month, year, seed, 40)
    
    # 输出生成的域名
    for domain in domains:
        print(domain)

if __name__ == "__main__":
    main()


#输入示例：
#python dga.py 14 5 2015 b6254bc3 