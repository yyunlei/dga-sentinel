import argparse
from datetime import datetime
from calendar import monthrange
import os

# 使用完整路径来确保不发生冲突
from datetime import date as DateType

def date2seed(d):
    year_prime = d.year
    month_prime = (d.month + 1)
    day_prime = d.day

    if month_prime > 12:
        month_prime -= 12
        year_prime += 1

    _, monthdays = monthrange(year_prime, month_prime) 
    if day_prime > monthdays:
        month_prime += 1
        day_prime -= monthdays

    if month_prime > 12:
        month_prime -= 12
        year_prime += 1

    date_prime = DateType(year_prime, month_prime, day_prime)  # 使用完整的类型名称
    epoch = datetime.strptime("1970-01-01", "%Y-%m-%d").date()
    return (date_prime - epoch).days

def dga(year, seed, counter, magic):
    seed_value = 10 * ((counter // 3 + seed) // 10)
    year_since = year - 1900
    random_numbers = []

    a = (magic >> counter) 
    b = (counter - 1) & 0xFF
    d = a * b & 0xFF
    e = d * seed_value 
    sld_length = 8 + (e & 1)

    magic_list = []
    for i in range(4):
        magic_list.append((magic >> (i * 8)) & 0xFF)
    for i in range(8):
        imod = i % 4
        idiv = i // 4
        b1 = (seed_value >> 8) & 0xFF
        b0 = seed_value & 0xFF
        if imod == 0:
            m = magic_list[idiv] >> 4
            f = (year_since >> idiv)
        elif imod == 1:
            m = magic_list[idiv] & 0xF 
            f = (year_since << idiv)
        elif imod == 2:
            m = magic_list[idiv] >> 4
            f = (b1 <<  idiv) ^ (b0 >> idiv)
        elif imod == 3:
            m = magic_list[idiv] & 0xF
            f = (b0 <<  idiv) ^ (b1 >> idiv)
        cp = (counter + 1)
        r = (m * f & 0xFF) * cp
        random_numbers.append(r & 0xFF)
    random_numbers.append(0xE0)
    r = random_numbers

    vowels = "aeiou"
    consonants = "bcdfghjklmnpqrstvwxyz"
    sld = ""

    while True:
        x = r.pop(0)
        if x & 0x80:
            sld += consonants[x % len(consonants)]
            if len(sld) >= sld_length:
                break
            x = r.pop(0)
            sld += vowels[x % len(vowels)]
            if len(sld) >= sld_length:
                break

            x = r[0]
            if x & 0x40:
                r.pop(0)
                sld += vowels[x % len(vowels)]
                if len(sld) >= sld_length:
                    break
        else:
            sld += vowels[x % len(vowels)]
            x = r.pop(0)
            sld += consonants[x % len(consonants)]
            if len(sld) >= sld_length:
                break

    tlds = ['com', 'org', 'biz', 'net', 'info', 'mobi', 'us', 'name', 'me']
   
    q = (counter ^ seed_value ^ magic) & 0xFFFFFFFF
    tld = tlds[q % len(tlds)]

    if len(sld) > 8:
        lc = sld[-1]
        sld = sld[:-1]
        if lc in consonants:
            sld_c = [sld + c for c in consonants]
        else:
            sld_c = [sld + c for c in vowels]
        return [s + "." + tld for s in sld_c]
    else:
        return sld + "." + tld

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DGA of Pitou")
    parser.add_argument("-d", "--date", 
                        help="Date for which to generate domains, e.g., 2019-04-09")
    parser.add_argument("-m", "--magic", choices=["0xDAFE02D", "0xDAFE02C"],
                        default="0xDAFE02C", help="Magic seed")
    parser.add_argument("-n", "--nr", type=int, default=20000,
                        help="Number of domains to generate")
    args = parser.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now()

    seed = date2seed(d)
    
    # 获取当前脚本所在的路径，确保输出文件在同级目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, "domain.txt")

    try:
        with open(output_file, 'w') as f:
            for c in range(args.nr):
                domains = dga(d.year, seed, c, int(args.magic, 16))
                if isinstance(domains, str):
                    f.write(domains + '\n')
                else:
                    for domain in domains:
                        f.write(domain + '\n')
        print(f"[+] Successfully generated {args.nr} domains and saved to '{output_file}'.")
    except IOError as e:
        print(f"[-] Failed to write to file '{output_file}'. Error: {e}")
