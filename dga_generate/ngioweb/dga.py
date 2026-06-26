from dataclasses import dataclass
import argparse
import os  # 导入os模块，用于处理文件路径

@dataclass
class Blocks:
    vowels = "aeiou"
    consonants = "bcdfghklmnprstvxz"
    prefix_words = ["un", "under", "re", "in", "im", "il", "ir", "en", "em", "over",
        "mis", "dis", "pre", "post", "anti", "inter", "sub", "ultra", "non", "de",
        "pro", "trans", "ex", "macro", "micro", "mini", "mono", "multi", "semi", "co"]
    vowel_words = ["able", "ant", "ate", "age", "ance", "ancy", "an", "ary", "al",
        "en", "ency", "er", "etn", "ed", "ese", "ern", "ize", "ify", "ing", "ish",
        "ity", "ion", "ian", "ism", "ist", "ic", "ical", "ible", "ive", "ite", "ish",
        "ian", "or", "ous", "ure"]
    consonant_words = ["dom", "hood", "less", "like", "ly", "fy", "ful", "ness",
        "ment", "sion", "ssion", "ship", "ty", "th", "tion", "ward"]
    tlds = [".net", ".info", ".com", ".biz", ".org", ".name"]


class Rand:
    def __init__(self, seed):
        self.seed = seed
        self.r = self.seed

    def rand(self, mod: int):
        self.r = (1103515245 * self.r + 12345) & 0xFFFFFFFF
        return self.r % mod

    def random_el_from_list(self, l: [str]) -> str:
        return l[self.rand(len(l))]


def ends_in_consonant(domain: str) -> bool:
    return domain[-1] not in Blocks.vowels


def dga(r):
    domain = ""
    nr_parts = r.rand(3) + 1
    for i in range(nr_parts):
        domain += r.random_el_from_list(Blocks.prefix_words)
        pick_vowel = ends_in_consonant(domain)
        for _ in range(r.rand(3) + 4):
            l = Blocks.vowels if pick_vowel else Blocks.consonants
            domain += r.random_el_from_list(l)
            pick_vowel ^= 1

        l = Blocks.vowel_words if ends_in_consonant(domain) else Blocks.consonant_words
        domain += r.random_el_from_list(l)
        domain += "-" if i < nr_parts - 1 else ""

    return domain + r.random_el_from_list(Blocks.tlds)


def main():
    """
    主函数，解析命令行参数，生成DGA域名，并将其写入文件。
    """
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-s",
        "--seed",
        help="Seed for the random generator (hex)",
        choices=["5397FB1", "56EDC15", "01275c63", "04bc65bc", "00375d5a"],
        default="56EDC15",
    )
    parser.add_argument("-n", "--nr", help="Number of domains to generate", default=20000, type=int)
    args = parser.parse_args()
    args.seed = int(args.seed, 16)

    r = Rand(args.seed)

    # 获取脚本所在的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, 'domains.txt')  # 构建输出文件路径

    # 打开文件以写入模式
    try:
        with open(output_file, 'w') as f:
            for i in range(args.nr):
                domain = dga(r)
                f.write(domain + '\n')  # 将域名写入文件
        print(f"[+] Successfully generated {args.nr} domains and saved to '{output_file}'.")
    except IOError as e:
        print(f"[-] Failed to write to file '{output_file}'. Error: {e}")

if __name__ == "__main__":
    main()
