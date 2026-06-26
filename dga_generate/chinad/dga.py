import string
import hashlib
import argparse
from datetime import datetime, timedelta
import os

def dga(date):
    TLDS = ['.com', '.org', '.net', '.biz', '.info', '.ru', '.cn']
    alphanumeric = string.ascii_lowercase + string.digits

    """
        Generates domains based on the date. By incrementing the date each time, we can generate more domains.
    """
    for nr in range(0x1000):  # 保持nr的范围不变
        data = "{}{}{}{}".format(
                chr(date.year % 100),
                chr(date.month),
                chr(date.day),
                chr(nr)) + 12*"\x00" 

        # 使用 utf-8 编码，避免编码问题
        h = hashlib.sha1(data.encode('utf-8')).digest()
        h = ''.join(map(chr, h))
        h_le = []
        for i in range(5):
            for j in range(4):
                h_le.append(h[i*4 + (3-j)])

        domain = ""
        for r in h_le[:16]: 
            domain += alphanumeric[(ord(r) & 0xFF) % len(alphanumeric)]

        r = ord(h_le[-4]) 
        domain += TLDS[r % len(TLDS)]
        yield domain

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gozi DGA")
    parser.add_argument("-d", "--date", help="Start date for which to generate domains (format: YYYY-MM-DD)")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 获取当前脚本所在目录
    current_directory = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_directory, 'domains.txt')

    # 打开文件准备写入
    with open(file_path, 'w') as f:
        count = 0
        while count < 20000:
            for domain in dga(d):
                if count >= 20000:  # 限制生成域名的数量为20000
                    break
                f.write(domain + '\n')
                count += 1
            # 增加日期种子，确保每次生成的域名不同
            d += timedelta(days=1)

    print(f"生成的20000个域名已写入 {file_path} 文件中。")
