#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
#-----------------------------------#
#                                   #
# Copyright (C) 2016 Azril Rahim    #
#                                   #
# Original author: Azril Rahim (upstream: github.com search "gameover dga azrilazam")               #
#                                   #
#-----------------------------------#
"""

import sys
import hashlib
import struct
import os
from typing import List

class GozDga:
    def __init__(self):
        self.imBE = self.isBE()

    def executeA(self, args: List[str]) -> int:
        """
        解析命令行参数并生成域名。

        参数:
            args (List[str]): 命令行参数列表。

        返回:
            int: 程序退出状态码。
        """
        numOfDomain = 0
        outfile = ""
        agStr = ""
        DD = 0
        MM = 0
        YY = 0
        dateAttack = ""

        # 合并所有参数为一个字符串，用空格分隔
        for i in range(1, len(args)):
            agStr += args[i] + " "

        # 替换 & 为 空格，并拆分为列表
        agStr = agStr.replace("&", " ")
        agStrL = agStr.strip().split()

        # 解析每个参数
        for ag, ag_item in enumerate(agStrL):
            ag_item = ag_item.strip()
            if not ag_item:
                continue
            argvL = ag_item.split("=")
            if len(argvL) != 2:
                print(f"Invalid argument for input #{ag}")
                return 0
            key, value = argvL
            if key == "n":
                try:
                    numOfDomain = int(value)
                except ValueError:
                    print(f"Invalid number for 'n': {value}")
                    return -1
                continue
            if key == "d":
                dateAttack = value
                dt = dateAttack.strip().split("-")
                if len(dt) != 3:
                    print("Invalid date format. Expected format: DD-MM-YYYY")
                    return -1
                try:
                    DD, MM, YY = map(int, dt)
                except ValueError:
                    print("Invalid date values. Day, month, and year should be integers.")
                    return -1
                continue
            if key == "f":
                outfile = value
                continue

        # 检查必要参数
        if numOfDomain == 0:
            print("GoZ: Missing or Invalid number of domain to be generated")
            return -1

        if not dateAttack.strip():
            print("Missing or Invalid date")
            return -1

        # 调用生成函数
        self.generate(numOfDomain, DD, MM, YY, outfile)
        return 0

    def generate(self, maxDomain: int, day: int, month: int, year: int, outfile: str):
        """
        生成域名并输出到文件或打印。

        参数:
            maxDomain (int): 要生成的域名数量。
            day (int): 日期中的日。
            month (int): 日期中的月。
            year (int): 日期中的年。
            outfile (str): 输出文件路径。如果为空，则打印到控制台。
        """
        domains = []
        # 检查字节序
        self.imBE = self.isBE()

        if outfile.strip():
            # 获取脚本所在的目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # 构建输出文件的完整路径
            outfile_path = os.path.join(script_dir, outfile)
            try:
                with open(outfile_path, 'w') as fs:
                    for id in range(maxDomain):
                        dgaDomainName = self.getDomainName(id, day, month, year)
                        fs.write(dgaDomainName + '\n')
                print(f"域名已生成并保存到 {outfile_path} 文件中。")
            except IOError as e:
                print(f"Error writing to file {outfile_path}: {e}")
        else:
            for id in range(maxDomain):
                dgaDomainName = self.getDomainName(id, day, month, year)
                print(dgaDomainName)

    def getDomainName(self, id: int, day: int, month: int, year: int) -> str:
        """
        根据 ID 和日期生成域名。

        参数:
            id (int): 域名编号。
            day (int): 日期中的日。
            month (int): 日期中的月。
            year (int): 日期中的年。

        返回:
            str: 生成的域名。
        """
        seedHex1 = self.getSeedHEX(id, day, month, year)
        domain = ""
        for mask in range(0, 16, 4):
            start = mask * 2
            seedHex2 = seedHex1[start:start+8]
            if len(seedHex2) < 8:
                seedHex2 = seedHex2.ljust(8, '0')  # 填充不足的部分
            seedInt = self.hexToInt(seedHex2)
            domain += self.getDomainPart(seedInt, 8)
        # 选择 TLD
        if id % 4 == 0:
            domain += ".com"
            return domain
        if id % 3 == 0:
            domain += ".org"
            return domain
        if id % 2 == 0:
            domain += ".biz"
            return domain
        domain += ".net"
        return domain

    def hexToInt(self, hex_str: str) -> int:
        """
        将十六进制字符串转换为整数，按字节顺序反转。

        参数:
            hex_str (str): 十六进制字符串。

        返回:
            int: 转换后的整数。
        """
        tmp = ""
        loc = len(hex_str)
        while loc > 0:
            start = max(0, loc - 2)
            tmp += hex_str[start:loc]
            loc -= 2
            if loc <= 0:
                break
        return int(tmp, 16)

    def toLE16(self, val: int) -> int:
        """
        将16位整数转换为小端字节序。

        参数:
            val (int): 原始整数。

        返回:
            int: 小端字节序的整数。
        """
        return struct.unpack("<H", struct.pack(">H", val))[0]

    def toLE32(self, val: int) -> int:
        """
        将32位整数转换为小端字节序。

        参数:
            val (int): 原始整数。

        返回:
            int: 小端字节序的整数。
        """
        return struct.unpack("<I", struct.pack(">I", val))[0]

    def isBE(self) -> bool:
        """
        检查系统是否为大端字节序。

        返回:
            bool: 如果是大端字节序，返回True；否则，返回False。
        """
        return sys.byteorder == 'big'

    def getSeedHEX(self, id: int, day: int, month: int, year: int) -> str:
        """
        根据 ID 和日期生成种子十六进制字符串。

        参数:
            id (int): 域名编号。
            day (int): 日期中的日。
            month (int): 日期中的月。
            year (int): 日期中的年。

        返回:
            str: MD5 哈希的十六进制表示。
        """
        md5 = hashlib.md5()
        key = b'\x01\x05\x19\x35'

        if self.imBE:
            id = self.toLE32(id)
            year = self.toLE16(year)
            day = self.toLE16(day)
            month = self.toLE16(month)

        # 将数据按顺序添加到 MD5 哈希
        md5.update(struct.pack("<I", id))
        md5.update(struct.pack("<H", year))
        md5.update(key)
        md5.update(struct.pack("<H", month))
        md5.update(key)
        md5.update(struct.pack("<H", day))
        md5.update(key)

        return md5.hexdigest()

    def getDomainPart(self, seed: int, maxSize: int) -> str:
        """
        根据种子生成域名的一部分。

        参数:
            seed (int): 种子整数。
            maxSize (int): 最大长度。

        返回:
            str: 域名的一部分。
        """
        tmpd = ""
        for _ in range(maxSize):
            edx = seed % 36
            seed = seed // 36
            if edx > 9:
                c = chr(ord('a') + (edx - 10))
            else:
                c = chr(ord('0') + edx)
            tmpd = c + tmpd
            if seed == 0:
                break
        return tmpd

def main():
    """
    主函数，创建 GozDga 实例并执行。
    """
    gozDga = GozDga()
    exit_code = gozDga.executeA(sys.argv)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

# 示例命令行调用:
# python dga.py n=100 d=01-01-2020 f=generated_domains.txt
