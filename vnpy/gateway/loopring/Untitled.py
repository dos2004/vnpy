[
    '315c4eeaa8b5f8aaf9174145bf43e1784b8fa00dc71d885a804e5ee9fa40b16349c146fb778cdf2d3aff021dfff5b403b510d0d0455468aeb98622b137dae857553ccd8883a7bc37520e06e515d22c954eba5025b8cc57ee59418ce7dc6bc41556bdb36bbca3e8774301fbcaa3b83b220809560987815f65286764703de0f3d524400a19b159610b11ef3e',
    '234c02ecbbfbafa3ed18510abd11fa724fcda2018a1a8342cf064bbde548b12b07df44ba7191d9606ef4081ffde5ad46a5069d9f7f543bedb9c861bf29c7e205132eda9382b0bc2c5c4b45f919cf3a9f1cb74151f6d551f4480c82b2cb24cc5b028aa76eb7b4ab24171ab3cdadb8356f',
    '32510ba9a7b2bba9b8005d43a304b5714cc0bb0c8a34884dd91304b8ad40b62b07df44ba6e9d8a2368e51d04e0e7b207b70b9b8261112bacb6c866a232dfe257527dc29398f5f3251a0d47e503c66e935de81230b59b7afb5f41afa8d661cb',
    '32510ba9aab2a8a4fd06414fb517b5605cc0aa0dc91a8908c2064ba8ad5ea06a029056f47a8ad3306ef5021eafe1ac01a81197847a5c68a1b78769a37bc8f4575432c198ccb4ef63590256e305cd3a9544ee4160ead45aef520489e7da7d835402bca670bda8eb775200b8dabbba246b130f040d8ec6447e2c767f3d30ed81ea2e4c1404e1315a1010e7229be6636aaa',
    '3f561ba9adb4b6ebec54424ba317b564418fac0dd35f8c08d31a1fe9e24fe56808c213f17c81d9607cee021dafe1e001b21ade877a5e68bea88d61b93ac5ee0d562e8e9582f5ef375f0a4ae20ed86e935de81230b59b73fb4302cd95d770c65b40aaa065f2a5e33a5a0bb5dcaba43722130f042f8ec85b7c2070',
    '32510bfbacfbb9befd54415da243e1695ecabd58c519cd4bd2061bbde24eb76a19d84aba34d8de287be84d07e7e9a30ee714979c7e1123a8bd9822a33ecaf512472e8e8f8db3f9635c1949e640c621854eba0d79eccf52ff111284b4cc61d11902aebc66f2b2e436434eacc0aba938220b084800c2ca4e693522643573b2c4ce35050b0cf774201f0fe52ac9f26d71b6cf61a711cc229f77ace7aa88a2f19983122b11be87a59c355d25f8e4',
    '32510bfbacfbb9befd54415da243e1695ecabd58c519cd4bd90f1fa6ea5ba47b01c909ba7696cf606ef40c04afe1ac0aa8148dd066592ded9f8774b529c7ea125d298e8883f5e9305f4b44f915cb2bd05af51373fd9b4af511039fa2d96f83414aaaf261bda2e97b170fb5cce2a53e675c154c0d9681596934777e2275b381ce2e40582afe67650b13e72287ff2270abcf73bb028932836fbdecfecee0a3b894473c1bbeb6b4913a536ce4f9b13f1efff71ea313c8661dd9a4ce',
    '315c4eeaa8b5f8bffd11155ea506b56041c6a00c8a08854dd21a4bbde54ce56801d943ba708b8a3574f40c00fff9e00fa1439fd0654327a3bfc860b92f89ee04132ecb9298f5fd2d5e4b45e40ecc3b9d59e9417df7c95bba410e9aa2ca24c5474da2f276baa3ac325918b2daada43d6712150441c2e04f6565517f317da9d3',
    '271946f9bbb2aeadec111841a81abc300ecaa01bd8069d5cc91005e9fe4aad6e04d513e96d99de2569bc5e50eeeca709b50a8a987f4264edb6896fb537d0a716132ddc938fb0f836480e06ed0fcd6e9759f40462f9cf57f4564186a2c1778f1543efa270bda5e933421cbe88a4a52222190f471e9bd15f652b653b7071aec59a2705081ffe72651d08f822c9ed6d76e48b63ab15d0208573a7eef027',
    '466d06ece998b7a2fb1d464fed2ced7641ddaa3cc31c9941cf110abbf409ed39598005b3399ccfafb61d0315fca0a314be138a9f32503bedac8067f03adbf3575c3b8edc9ba7f537530541ab0f9f3cd04ff50d66f1d559ba520e89a2cb2a83'
]

def hexstrxor(a, b):
    a = bytes.fromhex(a)
    b = bytes.fromhex(b)
    if len(a) > len(b):
       return "".join([hex(x ^ y)[2:].zfill(2) for (x, y) in zip(a[:len(b)], b)])
    else:
       return "".join([hex(x ^ y)[2:].zfill(2) for (x, y) in zip(a, b[:len(a)])])

def bruteforce(xored, table, deciphered):
    if len(xored) == 0:
        print(deciphered)
        return
    if ord(xored[0]) > 65 and ord(xored[0]) < 128:
        candidates = filter(lambda x: x[0] == xored[0], table)
        for c in candidates:
            #print(f"c is {c}")
            bruteforce(xored[1:], table, deciphered + c[1])
    else:
        bruteforce(xored[1:], table, deciphered + "*")


def bruteforce(xored, table, deciphered):
    if len(xored) == 0:
        print(deciphered)
        return
    candidates = list(filter(lambda x: x[0] == xored[0], table))
    if len(candidates) <= 10:
        for c in candidates:
            #print(f"c is {c}")
            if c[1] in plain_texts:
                bruteforce(xored[1:], table, deciphered + c[1])
    else:
        bruteforce(xored[1:], table, deciphered + "*")

[
orders[0]['exchangeId']:6
orders[0]['orderId']:108689
orders[0]['accountId']:13
orders[0]['tokenSId']:3
orders[0]['tokenBId']:2
orders[0]['amountS']:'87726711'
orders[0]['amountB']:'2866886000000000065536'
orders[0]['allOrNone']:'false'
orders[0]['buy']:'true'
orders[0]['validSince']:1587387080
orders[0]['validUntil']:1589979080
orders[0]['maxFeeBips']:50
orders[0]['label']:211
orders[0]['hash']:'20369766572472021066007920623674697249329985393664646442978859387982659724190'
orders[0]['signatureRx']:'4777535905384234077922714131458088873035998953316342016004388872442060644530'
orders[0]['signatureRy']:'21605629791715333147404662588260420831855629893382263810380861890184733738981'
orders[0]['signatureS']:'13992121398569925888346765673175846020998812359283178963129669325501666834630'
orders[0]['clientOrderId']:'200420215027000001'}
]
    "loopring.account.share": true,
    "loopring.account.share.folder" : "/tmp/",
    "loopring.account.orderId.caps" : 10,


f_in = open(".vntrader/vt_setting.json")
setting = json.load(f_in)
close(f_in)
setting["loopring.account.share"] = True
setting["loopring.account.share.folder"] = "/tmp"
setting["loopring.account.orderId.caps"] = 1
f_out = open(".vntrader/cta_strategy_setting.json", "w")
json.dump(a, f_out)

import gmpy2
from gmpy2 import mpz
import time, threading
lock = threading.Lock()

left = [{}]*16
right = {}
def inv(x, p):
    return gmpy2.invert(x, p)

def calc_left(h, g, p, id, e):
    for i in range(id*2**e, (id+1)*2**e):
        v = gmpy2.c_mod(gmpy2.mul(h, inv(gmpy2.powmod(g, i, p), p)), p) + p

def search_right(g, p):
    gB = gmpy2.powmod(g, B, p)
    for i in range(0, 2**20):
        if i % 2**14 == 0:
            print("r: ", i//2**14)
        v = gmpy2.powmod(gB, i, p)
        right[v] = i

p = mpz(13407807929942597099574024998205846127479365820592393377723561443721764030073546976801874298166903427690031858186486050853753882811946569946433649006084171)
g = mpz(11717829880366207009516117596335367088558084999998952205599979459063929499736583746670572176471460312928594829675428279466566527115212748467589894601965568)
h = mpz(3239475104050450443565264378728065788649097520952449527834792452971981976143292558073856937958553180532878928001494706097394108577585732452307673444020333)	
B = mpz(2**20)

print("start right")
tr = threading.Thread(target=search_right, name='search_right', args=(g, p))
tr.start()
tr.join()

print("start left")

tl = []
for i in range(0, 16):
    tl.append(threading.Thread(target=calc_left, name='calc_left', args=(h, g, p, i)))
for i in range(0, 16):
    tl[i].start()

for i in range(0, 16):
    tl[i].join()


from Crypto.Cipher import AES
import base64
import time
import gzip
from hashlib import md5
import sys
import io
import time, threading
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8', line_buffering=True)

def aeskey(key):
    return key + ' ' * (32 - len(key))

ct = base64.b64decode('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')

found=False
def calc_range(s, b):
    global found
    last_time = time.time()
    for i in range(s, b):
        key=f"{i}".zfill(8)
        if i % 100000==0:
            print("running 100000", key, "cost ", time.time() - last_time)
            last_time = time.time()
        if found:
            break
        try:
            cipher = AES.new(bytes(aeskey(key),encoding='utf-8'), AES.MODE_CBC, bytes(AES.block_size))
            gzip.decompress(bytes.strip(cipher.decrypt(ct)))
            print("pass: ", key)
            found=True
            break
        except:
            pass

tl = []
for i in range(0, 10):
    tl.append(threading.Thread(target=calc_range, name=f'calc_left_{i}', args=(i*10000000, (i+1)*10000000)))

for i in range(0, 10):
    tl[i].start()

for i in range(0, 10):
    tl[i].join()



# setpypath
# python ./examples/no_ui/market_account_report.py -e WEDEX;
# python ./examples/no_ui/market_account_report.py -e LOOPRING;
# python ./examples/no_ui/market_account_report.py -e OKEX;
# python ./examples/no_ui/market_account_report.py -e BINANCE

def calc_uniswap_bid_order_book(base_token_to_buy):
    # Buy base_token with quota_token
    outputAmount = base_token_to_buy
    inputReserve  = 445420256836899831808  # quota token
    outputReserve = 1325198976000000029360128   # base token
    # Output amount bought
    numerator = outputAmount * inputReserve * 1000
    denominator = (outputReserve - outputAmount) * 997
    quota_token_to_place = numerator / denominator + 1
    return quota_token_to_place

def calc_uniswap_ask_order_book(base_token_to_sell):
    # Sell base_token for quota_token
    inputAmount = base_token_to_sell
    inputReserve  = 1325198976000000029360128    # base token
    outputReserve = 445420256836899831808  # quota token
    # Output amount bought
    numerator = inputAmount * outputReserve * 997
    denominator = inputReserve * 1000 + inputAmount * 997
    outputAmount = numerator / denominator
    return outputAmount


import json
f = open('abi/factory.json')
factory_abi=json.load(f)
from web3 import Web3
from hashlib import md5
w3 = Web3(Web3.HTTPProvider("https://mainnet.infura.io/v3/c31352ced1014fb09d29b7f5d3c94fb3", request_kwargs={"timeout": 60}))
factory = w3.eth.contract(address="0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f", abi=factory_abi)
keep="0x85Eee30c52B0b379b046Fb0F85F4f3Dc3009aFEC"
weth="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
exchange_addr = factory.functions.getPair(keep, weth).call()


f = open('abi/erc20.abi')
erc20_abi = json.load(f)
keep_erc20 = w3.eth.contract(address=keep, abi=erc20_abi)
weth_erc20 = w3.eth.contract(address=weth, abi=erc20_abi)
keep_erc20.functions.balanceOf(exchange_addr).call()
weth_erc20.functions.balanceOf(exchange_addr).call()


def mimc(inp, steps, round_constants):
    start_time = time.time()
    for i in range(steps-1):
        inp = (inp**3 + round_constants[i % len(round_constants)]) % modulus
    print("MIMC computed in %.4f sec" % (time.time() - start_time))
    return inp

class PrimeField():
    def __init__(self, modulus):
        # Quick primality test
        assert pow(2, modulus, modulus) == 2
        self.modulus = modulus
    def add(self, x, y):
        return (x+y) % self.modulus
    def sub(self, x, y):
        return (x-y) % self.modulus
    def mul(self, x, y):
        return (x*y) % self.modulus

# Modular inverse using the extended Euclidean algorithm
def inv(self, a):
    if a == 0:
        return 0
    lm, hm = 1, 0
    low, high = a % self.modulus, self.modulus
    while low > 1:
        r = high//low
        nm, new = hm-lm*r, high-low*r
        lm, low, hm, high = nm, new, lm, low
    return lm % self.modulus

def multi_inv(self, values):
    partials = [1]
    for i in range(len(values)):
        partials.append(self.mul(partials[-1], values[i] or 1))
    inv = self.inv(partials[-1])
    outputs = [0] * len(values)
    for i in range(len(values), 0, -1):
        outputs[i-1] = self.mul(partials[i-1], inv) if values[i-1] else 0
        inv = self.mul(inv, values[i-1] or 1)
    return outputs

# Evaluate a polynomial at a point
def eval_poly_at(self, p, x):
    y = 0
    power_of_x = 1
    for i, p_coeff in enumerate(p):
        y += power_of_x * p_coeff
        power_of_x = (power_of_x * x) % self.modulus
    return y % self.modulus

def fft(vals, modulus, root_of_unity):
    if len(vals) == 1:
        return vals
    L = fft(vals[::2], modulus, pow(root_of_unity, 2, modulus))
    R = fft(vals[1::2], modulus, pow(root_of_unity, 2, modulus))
    o = [0 for i in vals]
    for i, (x, y) in enumerate(zip(L, R)):
        y_times_root = y*pow(root_of_unity, i, modulus)
        o[i] = (x+y_times_root) % modulus
        o[i+len(L)] = (x-y_times_root) % modulus
    return o

def inv_fft(vals, modulus, root_of_unity):
    f = PrimeField(modulus)
    # Inverse FFT
    invlen = f.inv(len(vals))
    return [(x*invlen) % modulus for x in
            fft(vals, modulus, f.inv(root_of_unity))]


def mod(a,b,m):
    result = 1
    base = a
    while (b>0):
         if b & 1==1:
            result = (result*base) % m
         base = (base*base) %m
         b = b >> 1
    return result


def bfs(start, equoation, result):
    if start == 10:
        res = eval(equoation)
        if eval(equoation) == -497:
            return True, f"{equoation} == {res}", res
        else:
            return False, f"{equoation} == {res}", res
    i = start
    for j in ["+", "-", "*", "/"]:
        r = result
        e = f"{equoation}{j}{i}"
        ok, e, res = bfs(i+1, e, r)
        if -497.1 < res < -496.9:
            print(e)
    return False, "", 0

"""5f4654140971c47658de19d62ba472b6"""

def hash(context):
    result = md5(bytes(context, 'utf8'))
    for i in range(0, 10_000_000):
        result = md5(result.digest())
    return result.hexdigest()

def hash2(context):
    result = md5(bytes(context, 'utf8'))
    for i in range(0, 2):
        dig = result.digest()
        result = md5(dig)
    return result.hexdigest()


stack = []
ins_len = [1] * 5 + [2] * 9 + [9, 1]
reg = [0] * 16
code = base64.b64decode('zyLpMs8CL9Oy/3QDdRlURZRGFHQHdRhURZFGIL/lv+MiNi+70AXRBtMD1wfYCNkJ5v3/iV14RWMB0n+/xgk=')
while True:
    ins, r0 = code[reg[15]] >> 4, code[reg[15]] & 15
    length = ins_len[ins]
    if length > 1:
        arg = code[reg[15] + 1 : reg[15] + length]
        if length == 2: r1 = arg[0] >> 4; r2 = arg[0] & 15
    reg[15] += length
    if 0 == ins : break
    elif 1 == ins : stack.append(reg[r0])
    elif 2 == ins : reg[r0] = stack.pop()
    elif 3 == ins : 
        if not reg[r0] : reg[15] += ins_len[code[reg[15]] >> 4]
    elif 4 == ins : reg[r0] = 0 if reg[r0] else 1
    elif 5 == ins : reg[r0] = reg[r1] + reg[r2]
    elif 6 == ins : reg[r0] = reg[r1] - reg[r2]
    elif 7 == ins : reg[r0] = reg[r1] * reg[r2]
    elif 8 == ins : reg[r0] = reg[r1] / reg[r2]
    elif 9 == ins : reg[r0] = reg[r1] % reg[r2]
    elif 10 == ins : reg[r0] = 1 if reg[r1] < reg[r2] else 0
    elif 11 == ins : stack.append(reg[r0]); reg[r0] += int.from_bytes(arg, byteorder='little', signed=True)
    elif 12 == ins : reg[r0] += int.from_bytes(arg, byteorder='little', signed=True)
    elif ins in (13, 14) : reg[r0] = int.from_bytes(arg, byteorder='little', signed=True)

key = str(reg[0])+str(reg[1])
