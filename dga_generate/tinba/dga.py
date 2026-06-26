def dga(seed, domain, tlds, num_domains):
    # Initialize seed and ensure it has a correct length
    seed += (17 - len(seed)) * '\x00'
    seed_l = [ord(s) for s in seed]
    
    yield domain  # Yield the first domain
    
    for _ in range(num_domains):
        domain_l = [ord(l) for l in domain]
        seed_sum = sum(seed_l[:16])
        new_domain = []
        tmp = seed_l[15] & 0xFF
        
        # Generate the new domain characters based on the current seed
        for i in range(12):
            while True:
                tmp += domain_l[i]
                tmp ^= (seed_sum & 0xFF)
                tmp += domain_l[i+1]
                tmp &= 0xFF
                if 0x61 < tmp < 0x7a:  # Check if the character is a lowercase letter
                    new_domain.append(tmp)
                    break
                else:
                    seed_sum += 1  # If not valid, adjust the sum

        base_domain = ''.join([chr(x) for x in new_domain])
        
        # Append the TLDs
        for tld in tlds:
            domain = base_domain + '.' + tld
            yield domain


if __name__ == '__main__':
    # DGA configurations (predefined seed, domain, TLDs, and number of domains to generate)
    dga_configurations = [
        ('oGkS3w3sGGOGG7oc', 'ssrgwnrmgrxe.com', ('com',), 2000),
        ('jc74FlUna852Ji9o', 'blackfreeqazyio.cc', ('com', 'net', 'in', 'ru'), 2000),
        ('yqokqFC2TPBFfJcG', 'watchthisnow.xyz', ('pw', 'us', 'xyz', 'club'), 2000),
        ('j193HsnW72Yqns7u', 'j193hsne720uie8i.cc', ('com', 'net', 'biz', 'org'), 2000),
    ]

    # Hardcoded domains (from various sources)
    hard_coded = [
        'newstatinru.ru', 'justforyou0987.pw', 'phpsitegooddecoder.com',
        'santaluable.com', 'santanyr.com', 'ervaluable.com', 'larnasa.com'
    ]

    # Open file to write the domains
    with open('domains.txt', 'w') as f:
        # Write hardcoded domains first
        for domain in hard_coded:
            f.write(domain + '\n')
        
        # Generate domains from DGA configurations
        for config in dga_configurations:
            for result in dga(*config):
                f.write(result + '\n')

    print("20000 domains have been written to 'domains.txt'")
