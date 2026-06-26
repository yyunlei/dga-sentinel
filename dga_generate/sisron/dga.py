from datetime import datetime, timedelta
import base64
import argparse

def dga(d, day_index, tld_index):
    # 使用 tlds 数组包含所有后缀
    tlds = [x.encode('ascii') for x in [".com", ".org", ".net", ".info"]]
    
    # 调整日期
    d -= timedelta(days=day_index)
    
    # 格式化日期
    ds = d.strftime("%d%m%Y").encode('latin1')
    
    # 生成域名
    domain = base64.b64encode(ds).lower().replace(b"=", b"a") + tlds[tld_index % len(tlds)]  # 保证 tld_index 在有效范围内
    return domain.decode('latin1')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", help="date for which to generate domains")
    args = parser.parse_args()
    
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    # 打开文件准备写入域名
    with open("domains.txt", "w") as file:
        for i in range(20000):  # 生成 20000 个域名
            domain = dga(d, i % 10, i // 10)  # 使用 i//10 作为 tld_index
            file.write(domain + "\n")  # 写入域名到文件

    print("20000 domains have been written to 'domains.txt'")
