import argparse
from datetime import datetime
import os  # 导入os模块，用于处理文件路径

def generate_necurs_domain(sequence_nr, magic_nr, date):
    """
    生成类似Necurs的DGA域名。
    
    参数:
        sequence_nr (int): 序列号，用于生成不同的域名。
        magic_nr (int): 魔法数字，用于增加生成域名的复杂性。
        date (datetime): 当前日期，用于生成基于日期的种子。
    
    返回:
        str: 生成的域名。
    """
    def pseudo_random(value):
        """
        简单的伪随机数生成器，通过多次迭代修改输入值。
        
        参数:
            value (int): 初始值。
        
        返回:
            int: 修改后的伪随机数。
        """
        loops = (value & 0x7F) + 21  # 计算循环次数
        for index in range(loops):
            value += ((value * 7) ^ (value << 15)) + 8 * index - (value >> 5)
            value &= ((1 << 64) - 1)  # 保持值在64位范围内
        return value

    def mod64(nr1, nr2):
        """
        计算nr1对nr2的模。
        
        参数:
            nr1 (int): 被除数。
            nr2 (int): 除数。
        
        返回:
            int: 模的结果。
        """
        return nr1 % nr2

    # 生成种子值
    n = pseudo_random(date.year)
    n = pseudo_random(n + date.month + 43690)
    n = pseudo_random(n + (date.day >> 2))
    n = pseudo_random(n + sequence_nr)
    n = pseudo_random(n + magic_nr)
    domain_length = mod64(n, 15) + 7  # 确定域名长度（7到21字符）

    domain = ""
    for i in range(domain_length):
        n = pseudo_random(n + i)
        ch = mod64(n, 25) + ord('a')  # 生成一个小写字母（a-y）
        domain += chr(ch)
        n += 0xABBEDF
        n = pseudo_random(n)

    # 定义常见的顶级域名（TLD）
    tlds = [
        'tj', 'in', 'jp', 'tw', 'ac', 'cm', 'la', 'mn', 'so', 'sh', 'sc', 'nu',
        'nf', 'mu', 'ms', 'mx', 'ki', 'im', 'cx', 'cc', 'tv', 'bz', 'me', 'eu',
        'de', 'ru', 'co', 'su', 'pw', 'kz', 'sx', 'us', 'ug', 'ir', 'to', 'ga',
        'com', 'net', 'org', 'biz', 'xxx', 'pro', 'bit'
    ]

    tld = tlds[mod64(n, len(tlds))]  # 根据当前n值选择TLD
    domain += '.' + tld  # 组合生成完整域名
    return domain

def main():
    """
    主函数，解析命令行参数，生成DGA域名，并将其写入文件。
    """
    parser = argparse.ArgumentParser(
        description="Generate Necurs-like DGA domains and save to domains.txt"
    )
    parser.add_argument(
        "-d", "--date",
        help="Specify the date as YYYY-mm-dd. If not provided, current date is used.",
        type=str
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
            for sequence_nr in range(20000):  # 修改为生成20,000个域名
                domain = generate_necurs_domain(sequence_nr, 9, date)
                f.write(domain + '\n')  # 将域名写入文件
        print(f"[+] Successfully generated 20,000 domains and saved to '{output_file}'.")
    except IOError as e:
        print(f"[-] Failed to write to file '{output_file}'. Error: {e}")

if __name__ == "__main__":
    main()
