import argparse

def get_next_domain(domain):
    qwerty = 'qwertyuiopasdfghjklzxcvbnm123945678'

    def sum_of_characters(domain):
        return sum([ord(d) for d in domain[:-3]])

    sof = sum_of_characters(domain)
    ascii_codes = [ord(d) for d in domain] + 100*[0]
    old_hostname_length = len(domain) - 4
    for i in range(0, 66):
        for j in range(0, 66):
            edi = j + i
            if edi < 65:
                p = (old_hostname_length * ascii_codes[j]) 
                cl = p ^ ascii_codes[edi] ^ sof
                ascii_codes[edi] = cl & 0xFF

    # Calculate the new hostname length
    cx = ((ascii_codes[2]*old_hostname_length) ^ ascii_codes[0]) & 0xFF
    hostname_length = int(cx/16) # at most 15
    if hostname_length < 10:
        hostname_length = old_hostname_length

    # Generate hostname
    for i in range(hostname_length):
        index = int(ascii_codes[i]/8) # max 31 --> last 3 chars of qwerty unreachable
        bl = ord(qwerty[index])
        ascii_codes[i] = bl

    hostname = ''.join([chr(a) for a in ascii_codes[:hostname_length]])

    # Append .net or .com (alternating)
    tld = '.com' if domain.endswith('.net') else '.net'
    domain = hostname + tld

    return domain

if __name__ == "__main__":
    """ Example seed domain: 4ypv1eehphg3a.com """
    parser = argparse.ArgumentParser(description="DGA of Shiotob")
    parser.add_argument("domain", help="initial domain")
    parser.add_argument(
        "-n", "--num_domains", help="number of domains to generate", type=int, default=20000
    )
    args = parser.parse_args()
    domain = args.domain

    # Write 20000 domains to domains.txt file
    with open("domains.txt", "w") as file:
        for _ in range(args.num_domains):
            file.write(domain + "\n")
            domain = get_next_domain(domain)

    print(f"{args.num_domains} domains have been written to 'domains.txt'")
