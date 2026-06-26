length = 7
tld = "com"
key = "1676d5775e05c50b46baa5579d4fc7"
base = 0x45AE94B2

consonants = "qwrtpsdfghjklzxcvbnmv"
vowels = "eyuioa"

# 计算 step 值
step = 0
for m in key:
    step += ord(m)

# 创建并打开文件，准备写入域名
with open("domains.txt", "w") as file:
    for nr in range(20000):
        domain = ""
        base += step

        # 生成域名
        for i in range(length):
            index = int(base / (3 + 2 * i))
            if i % 2 == 0:
                char = consonants[index % 20]
            else:
                char = vowels[index % 6]
            domain += char

        domain += "." + tld
        
        # 将生成的域名写入文件
        file.write(domain + "\n")

print("20000 domains have been written to 'domains.txt'")
